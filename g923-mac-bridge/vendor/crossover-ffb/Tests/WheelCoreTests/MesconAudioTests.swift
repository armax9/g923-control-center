import XCTest
import Darwin
@testable import WheelCore
final class MesconAudioTests:XCTestCase {
    func packet(_ values:[Float],live:Bool=true)->[UInt8] {
        var b=Array("G9AU".utf8)+[1,live ? 1:0,UInt8(values.count),0,1,0,0,0]
        for var f in values { withUnsafeBytes(of:&f) { b += $0 } }
        return b
    }
    func testAcceptsBoundedAudioAndPause() {
        XCTAssertEqual(MesconAudioFrame.decode(packet([0.25,-0.5]))?.samples,[0.25,-0.5])
        XCTAssertEqual(MesconAudioFrame.decode(packet([0],live:false))?.live,false)
    }
    func testRejectsTruncatedOrForeign() {
        XCTAssertNil(MesconAudioFrame.decode([0,1]))
        var b=packet([0.5]);b[0]=0;XCTAssertNil(MesconAudioFrame.decode(b))
        XCTAssertNil(MesconAudioFrame.decode(Array(packet([0.5]).dropLast())))
    }
    func testRejectsNaNInfinityAndOverflow() {
        for f:Float in [.nan,.infinity,1.01,-1.01] {XCTAssertNil(MesconAudioFrame.decode(packet([f])))}
        XCTAssertNil(MesconAudioFrame.decode(packet(Array(repeating:0,count:13))))
    }
    func testLoopbackFreshnessAndTimeout() throws {
        let port=UInt16(40000+getpid()%10000)
        let receiver=try MesconAudioReceiver(port:port)
        let fd=socket(AF_INET,SOCK_DGRAM,0);XCTAssertGreaterThanOrEqual(fd,0);defer{close(fd)}
        var destination=sockaddr_in();destination.sin_len=UInt8(MemoryLayout<sockaddr_in>.size);destination.sin_family=sa_family_t(AF_INET);destination.sin_port=port.bigEndian;destination.sin_addr.s_addr=inet_addr("127.0.0.1")
        let b=packet([0.25,-0.5])
        let count=b.withUnsafeBytes{buffer in withUnsafePointer(to:&destination){$0.withMemoryRebound(to:sockaddr.self,capacity:1){sendto(fd,buffer.baseAddress,buffer.count,0,$0,socklen_t(MemoryLayout<sockaddr_in>.size))}}}
        XCTAssertEqual(count,b.count)
        var frame=receiver.poll(now:10)
        for _ in 0..<1000 { if frame.live {break};usleep(1000);frame=receiver.poll(now:10) }
        XCTAssertTrue(frame.live);XCTAssertEqual(frame.samples,[0.25,-0.5])
        XCTAssertFalse(receiver.poll(now:10.501).live)
        XCTAssertTrue(receiver.poll(now:11).samples.allSatisfy{$0==0})
    }
}
