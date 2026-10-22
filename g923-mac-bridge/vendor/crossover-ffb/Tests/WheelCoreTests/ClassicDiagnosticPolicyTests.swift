import XCTest
@testable import WheelCore
final class ClassicDiagnosticPolicyTests:XCTestCase {
 func testFrictionCannotDriveMotorInDirectionalPhase(){
  var state=BridgeForceState();state.acquired=true;state.effects=[BridgeEffect(slot:0,kind:.constant,params:[0]),BridgeEffect(slot:1,kind:.friction,params:[0,10000,10000,10000,10000,0])]
  let filtered=ClassicDiagnosticPolicy.directionalOnly(state)
  XCTAssertEqual(state.effects.count,2);XCTAssertEqual(filtered.effects.count,1)
  let engine=EffectEngine()
  for v in [-1.0,-0.01,0,0.01,1] { XCTAssertEqual(engine.force(filtered,wheel:WheelKinematics(velocity:v),now:10),0) }
 }
 func testGameConstantForcePreserved(){
  var state=BridgeForceState();state.effects=[BridgeEffect(slot:0,kind:.constant,params:[5000])]
  XCTAssertEqual(EffectEngine().force(ClassicDiagnosticPolicy.directionalOnly(state),wheel:WheelKinematics(),now:10),-0.5,accuracy:0.0001)
 }
}
