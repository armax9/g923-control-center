// SPDX-License-Identifier: GPL-3.0-only
import Foundation
import Darwin
import WheelCore
func labLog(_ value: [String:Any]) {
 var value = value; value["uptime_ms"] = Int64(ProcessInfo.processInfo.systemUptime * 1000)
 value["unix_ms"] = SharedBridge.nowMilliseconds()
 if let data = try? JSONSerialization.data(withJSONObject:value,options:[.sortedKeys]) {
  FileHandle.standardOutput.write(data);FileHandle.standardOutput.write(Data([10]))
 }
}
let args=Array(CommandLine.arguments.dropFirst())
if args == ["--dry-run"] { labLog(["event":"plan","hardware_used":false,"trueforce_enabled":false,"strength":0.25]);exit(0) }
guard args.count>=3,args[0]=="--map",args[1].hasPrefix("/"),args[2]=="--user-ready" else { fputs("Explicit map and readiness required\n",stderr);exit(2) }
var tfMotorSign:Double?;var mesconPort:UInt16?;var calibration=false;var motorSign:Double?;var fullEffects=false;var requestedStrength=0.25;var requestedLimit=1.0
var sdkForceSign=1.0
var sdkForceFile:String?
var crossFFBClassic=false
var slotUpdates=false
var i=3
while i<args.count {
 switch args[i] {
 case "--tf-motor-sign":
  guard i+1<args.count,let n=Double(args[i+1]),n == -1 || n == 1 else {exit(2)}
  tfMotorSign=n;i+=2
 case "--mescon-audio":
  guard i+1<args.count,let port=UInt16(args[i+1]),port>0 else {exit(2)}
  mesconPort=port;i+=2
 case "--calibrate":calibration=true;i+=1
 case "--sdk-force-sign":
  guard i+1<args.count,let n=Double(args[i+1]),n == -1 || n == 1 else {exit(2)}
  sdkForceSign=n;i+=2
 case "--sdk-force-file":
  guard i+1<args.count,args[i+1].hasPrefix("/") else {exit(2)}
  sdkForceFile=args[i+1];i+=2
 case "--crossffb-classic":crossFFBClassic=true;i+=1
 case "--classic-slot-updates":slotUpdates=true;i+=1
 case "--all-effects":fullEffects=true;i+=1
 case "--motor-sign":
  guard i+1<args.count,let n=Double(args[i+1]),n == -1 || n == 1 else {exit(2)}
  motorSign=n;i+=2
 case "--max-force":
  guard i+1<args.count,let n=Double(args[i+1]),n.isFinite,n>0,n<=1 else {exit(2)}
  requestedLimit=n;i+=2
 case "--strength":
  guard i+1<args.count,let n=Double(args[i+1]),n.isFinite,n>0,n<=1 else {exit(2)}
  requestedStrength=n;i+=2
 default:exit(2)
 }
}
guard !(calibration && (fullEffects || motorSign != nil)), !fullEffects || motorSign != nil else {exit(2)}
guard sdkForceFile == nil || (mesconPort == nil && !calibration) else {exit(2)}
guard !crossFFBClassic || (mesconPort == nil && sdkForceFile == nil && !slotUpdates && !calibration) else {exit(2)}
let lockPath="/tmp/g923-mac-bridge-\(getuid()).lock"
let lockFD=open(lockPath,O_CREAT|O_RDWR|O_NOFOLLOW|O_CLOEXEC,0o600)
var info=stat()
guard lockFD >= 0, fstat(lockFD,&info)==0,info.st_uid==getuid(),(info.st_mode&S_IFMT)==S_IFREG,flock(lockFD,LOCK_EX|LOCK_NB)==0 else { fputs("Motor lock unavailable\n",stderr);exit(3) }
let bridge=FFBBridge(sharedPath:args[1])
var tf=FFBBridge.TrueForceSettings();tf.enabled=mesconPort != nil;tf.strength=1;bridge.trueForce=tf
bridge.mesconAudioPort=mesconPort
bridge.strength=requestedStrength
bridge.maxForce=requestedLimit
bridge.allEffects=fullEffects
bridge.classicSlotUpdates=slotUpdates
bridge.crossFFBClassic=crossFFBClassic
bridge.sdkForceFile=sdkForceFile
bridge.sdkForceSign=sdkForceSign
if let motorSign { bridge.motorSign=motorSign }
if let tfMotorSign { bridge.tfMotorSign=tfMotorSign }
var wheel=WheelSettings();wheel.centeringSpring=false;wheel.springInFFBGames=false;wheel.revLights=false;bridge.wheel=wheel
signal(SIGINT,SIG_IGN);signal(SIGTERM,SIG_IGN)
let interrupt=DispatchSource.makeSignalSource(signal:SIGINT,queue:.main)
let terminate=DispatchSource.makeSignalSource(signal:SIGTERM,queue:.main)
let stop: @Sendable ()->Void = { bridge.stop();labLog(["event":"bridge_stopped","physical_stop_confirmed":false]);close(lockFD);exit(0) }
interrupt.setEventHandler(handler:stop);terminate.setEventHandler(handler:stop);interrupt.resume();terminate.resume()
labLog(["event":"classic_bridge_start","mapping":args[1],"strength":requestedStrength,"max_force":requestedLimit,"trueforce_enabled":mesconPort != nil,"telemetry_emulation":mesconPort != nil,"artificial_spring_enabled":false,"conditions_enabled":fullEffects,"crossffb_classic_profile":crossFFBClassic,"classic_slot_updates":slotUpdates,"sdk_force_sink":sdkForceFile != nil,"sdk_force_sign":sdkForceSign,"motor_sign":bridge.motorSign,"calibration":calibration])
if calibration {
 bridge.onCalibrated = { sign,viaTF in
  labLog(["event":"motor_direction_result","valid":sign != nil,"sign":sign ?? 0,"via_trueforce":viaTF])
  DispatchQueue.main.async { bridge.stop();close(lockFD);exit(sign == nil ? 4 : 0) }
 }
 bridge.requestCalibration()
}
bridge.start()
RunLoop.main.run()
