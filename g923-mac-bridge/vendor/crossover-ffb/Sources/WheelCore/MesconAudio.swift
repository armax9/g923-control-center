// SPDX-License-Identifier: MIT
// Independent IPC receiver; GPL-2.0 synthesis remains in its separate process.
import Foundation
import Darwin
public struct MesconAudioFrame: Equatable {
    public var live: Bool
    public var sequence: UInt32
    public var samples: [Double]
    public static func decode(_ b: [UInt8]) -> Self? {
        guard b.count >= 12, Array(b[0..<4]) == Array("G9AU".utf8), b[4] == 1, b[5] <= 1 else { return nil }
        let n=Int(b[6]) | Int(b[7])<<8
        guard (1...12).contains(n), b.count == 12+n*4 else { return nil }
        func word(_ i:Int)->UInt32 { UInt32(b[i]) | UInt32(b[i+1])<<8 | UInt32(b[i+2])<<16 | UInt32(b[i+3])<<24 }
        let samples=(0..<n).map { Double(Float(bitPattern:word(12+$0*4))) }
        guard samples.allSatisfy({ $0.isFinite && abs($0)<=1 }) else { return nil }
        return Self(live:b[5]==1,sequence:word(8),samples:samples)
    }
}
public final class MesconAudioReceiver {
    private let fd:Int32
    private var lastTime=0.0
    private var lastLive=false
    public init(port:UInt16) throws {
        fd=socket(AF_INET,SOCK_DGRAM,0)
        guard fd>=0 else { throw POSIXError(.EIO) }
        var address=sockaddr_in();address.sin_len=UInt8(MemoryLayout<sockaddr_in>.size);address.sin_family=sa_family_t(AF_INET);address.sin_port=port.bigEndian;address.sin_addr.s_addr=inet_addr("127.0.0.1")
        let result=withUnsafePointer(to:&address){$0.withMemoryRebound(to:sockaddr.self,capacity:1){Darwin.bind(fd,$0,socklen_t(MemoryLayout<sockaddr_in>.size))}}
        guard result==0 else {let e=errno;close(fd);throw POSIXError(POSIXErrorCode(rawValue:e) ?? .EIO)}
        _=fcntl(fd,F_SETFL,O_NONBLOCK)
    }
    deinit {close(fd)}
    public func poll(now:Double)->(live:Bool,samples:[Double]) {
        var latest:[Double]=[];var bytes=[UInt8](repeating:0,count:1024)
        for _ in 0..<64 {
            let n=recv(fd,&bytes,bytes.count,0)
            if n<0 {break}
            if let frame=MesconAudioFrame.decode(Array(bytes.prefix(n))) {lastTime=now;lastLive=frame.live;latest=frame.samples}
        }
        return (lastLive && now-lastTime<0.5,latest.isEmpty ? [Double](repeating:0,count:8):latest)
    }
}
