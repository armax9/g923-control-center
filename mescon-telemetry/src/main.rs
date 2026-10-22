// SPDX-License-Identifier: GPL-2.0-only
// macOS telemetry/audio IPC adapter. Original EngineSynth is in synth.rs.
mod synth;
mod control;
mod effects; mod telemetry; mod codemasters; mod pcars; mod beamng; mod f1; mod wrc;
use std::{net::UdpSocket,time::{Instant,Duration},thread,env};
use effects::{Mixer,EffectGains};
type State = telemetry::Telemetry;
fn relay_id(b:&[u8])->bool {
 ["ets2","ats","iracing","raceroom","assetto","acc","ac-evo","lmu","rf2","relay"].iter().any(|id| {
 let mut field=[0u8;8];field[..id.len()].copy_from_slice(id.as_bytes()); b==field
 })
}
fn decode(b:&[u8])->Option<State>{
 if b.len()<28||&b[..4]!=b"LTFR"||b[4]!=2||!relay_id(&b[6..14]){return None}
 let f=|i|f32::from_le_bytes(b[i..i+4].try_into().unwrap());
 let rpm=f(14);let limit=f(18);let throttle=f(22);
 if !rpm.is_finite()||!limit.is_finite()||!throttle.is_finite()||!(0.0..=20000.).contains(&rpm)||!(0.0..=20000.).contains(&limit)||!(0.0..=1.).contains(&throttle){return None}
 let extra=|offset:usize| if b.len()>=offset+4 {f(offset)} else {0.};
 let speed=extra(32);let brake=extra(36);
 if !speed.is_finite()||!brake.is_finite(){return None}
 Some(State{rpm:if limit>0.0{rpm}else{0.0},max_rpm:limit,throttle,speed,brake:brake.clamp(0.,1.),gear:i16::from_le_bytes([b[26],b[27]]).clamp(-1,20) as i8,airborne:b[5]&1!=0,..Default::default()})
}
fn audio(samples:&[f32],valid:bool,seq:u32)->Vec<u8>{
 let mut b=Vec::from(&b"G9AU"[..]);b.push(1);b.push(valid as u8);b.extend_from_slice(&(samples.len() as u16).to_le_bytes());b.extend_from_slice(&seq.to_le_bytes());
 for s in samples {b.extend_from_slice(&s.clamp(-1.,1.).to_le_bytes())}b
}
fn main()->std::io::Result<()>{
 let a:Vec<String>=env::args().collect();let arg=|name:&str,default:&str|a.iter().position(|s|s==name).and_then(|i|a.get(i+1)).cloned().unwrap_or(default.to_string());
 let intensity:f32=arg("--intensity","0.1").parse().expect("intensity");assert!(intensity.is_finite()&&(0.0..=1.).contains(&intensity));
 let control_path=a.iter().position(|s|s=="--control-file").and_then(|i|a.get(i+1)).map(std::path::PathBuf::from);
 let mut gain=control::LiveGain::new(control_path,intensity);
 let cylinders:u8=arg("--cylinders","6").parse().expect("cylinders");assert!((1..=16).contains(&cylinders));
 let source=arg("--source","relay");
 let port=match source.as_str(){"relay"=>20780,"codemasters"|"f1"|"wrc"=>20777,"pcars"=>5606,"beamng"=>4444,_=>panic!("unknown telemetry source")};
 // Optional diagnostic relay; default ports and synthesis remain unchanged.
 let port:u16=arg("--listen-port",&port.to_string()).parse().map_err(|_|std::io::Error::new(std::io::ErrorKind::InvalidInput,"invalid listen port"))?;
 if port==0{return Err(std::io::Error::new(std::io::ErrorKind::InvalidInput,"listen port must be nonzero"))}
 let input=UdpSocket::bind(("127.0.0.1",port))?;input.set_nonblocking(true)?;
 let mut f1_decoder=f1::Decoder::new();let mut beamng_decoder=beamng::Decoder::new();
 let output_port:u16=arg("--output-port","20781").parse().map_err(|_|std::io::Error::new(std::io::ErrorKind::InvalidInput,"invalid output port"))?;
 if output_port==0{return Err(std::io::Error::new(std::io::ErrorKind::InvalidInput,"output port must be nonzero"))}
 let output=UdpSocket::bind("127.0.0.1:0")?;output.connect(("127.0.0.1",output_port))?;
 let mut state=State::default();let mut received:Option<Instant>=None;let mut engine=if arg("--effects","engine")=="all"{Mixer::new(cylinders,1.,EffectGains::default())}else{Mixer::engine_only(cylinders,1.,EffectGains::default())};let mut seq=0u32;let mut count=0u64;let mut invalid=0u64;let mut lastlog=Instant::now();let mut next=Instant::now();
 println!("{{\"event\":\"synth_start\",\"mode\":\"telemetry_emulation\",\"hardware_output\":false,\"intensity\":{intensity},\"cylinders\":{cylinders}}}");
 loop {
  if let Some(level)=gain.poll(Instant::now()){println!("{{\"event\":\"engine_intensity\",\"intensity\":{level},\"live_update\":true}}");}
  let mut buf=[0u8;4096];
  for _ in 0..128{match input.recv(&mut buf){Ok(n)=>{let packet=&buf[..n];
 let parsed=match source.as_str(){
 "relay"=>decode(packet),
 _=>{
 let result=match source.as_str(){"codemasters"=>codemasters::parse(packet),"pcars"=>pcars::parse(packet),"beamng"=>beamng_decoder.parse(packet),"f1"=>f1_decoder.parse(packet),"wrc"=>wrc::parse(packet),_=>None};
 result.and_then(|(_,t)|if t.rpm.is_finite()&&t.throttle.is_finite()&&t.max_rpm.is_finite()&&(0.0..=30000.).contains(&t.rpm)&&t.max_rpm>0.0 {Some(State{throttle:t.throttle.clamp(0.,1.),..t})}else{None})
 }};
 if let Some(t)=parsed{state=t;received=Some(Instant::now());count+=1}else{invalid+=1}},Err(e) if e.kind()==std::io::ErrorKind::WouldBlock=>break,Err(e)=>return Err(e)}}
  let live=received.map(|t|t.elapsed()<Duration::from_millis(500)).unwrap_or(false)&&state.rpm>0.;
  let level=gain.next(0.002);
  let note=if live{state}else{State::default()};let mut samples=Vec::with_capacity(8);engine.render(&note,if live{level}else{0.},8,&mut samples);seq=seq.wrapping_add(1);let _=output.send(&audio(&samples,live,seq));
  if lastlog.elapsed()>=Duration::from_secs(1){println!("{{\"event\":\"telemetry\",\"packets\":{count},\"invalid\":{invalid},\"live\":{live},\"rpm\":{},\"throttle\":{}}}",state.rpm,state.throttle);lastlog=Instant::now()}
  next+=Duration::from_millis(2);let now=Instant::now();if next>now{thread::sleep(next-now)}else{next=now}
 }
}
#[cfg(test)]mod adapter_tests{use super::*;
 fn packet(rpm:f32)->Vec<u8>{let mut b=vec![0;40];b[..4].copy_from_slice(b"LTFR");b[4]=2;b[6..10].copy_from_slice(b"ets2");b[14..18].copy_from_slice(&rpm.to_le_bytes());b[18..22].copy_from_slice(&2500f32.to_le_bytes());b[22..26].copy_from_slice(&0.5f32.to_le_bytes());b}
 #[test]fn rejects_invalid_and_foreign(){assert!(decode(&packet(900.)).is_some());assert!(decode(&packet(f32::NAN)).is_none());let mut b=packet(900.);b[6]=b'x';assert!(decode(&b).is_none());assert!(decode(&[0;10]).is_none())}
 #[test]fn audio_format_and_clamp(){let b=audio(&[2.,-2.],true,12);assert_eq!(b.len(),20);assert_eq!(&b[..4],b"G9AU");assert_eq!(f32::from_le_bytes(b[12..16].try_into().unwrap()),1.);assert_eq!(b[5],1)}
}
