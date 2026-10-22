import XCTest
@testable import WheelCore
final class ConditionContractTests:XCTestCase {
 func output(_ kind:BridgeEffect.Kind,_ params:[Int32],_ k:WheelKinematics)->Double {
  var s=BridgeForceState();s.effects=[BridgeEffect(slot:0,kind:kind,params:params)]
  return EffectEngine().force(s,wheel:k,now:1)
 }
 func testZeroSaturationMeansZeroForce(){
  for kind:BridgeEffect.Kind in [.spring,.damper,.inertia,.friction] {
   for sign in [-1.0,1] {XCTAssertEqual(output(kind,[0,10000,10000,0,0,0],WheelKinematics(position:sign,velocity:sign,acceleration:sign*40)),0)}
  }
 }
 func testAsymmetricSaturationAndOffsetDeadband(){
  let p:[Int32]=[1000,10000,5000,2000,1000,500]
  XCTAssertEqual(output(.spring,p,WheelKinematics(position:0.1)),0)
  XCTAssertEqual(output(.spring,p,WheelKinematics(position:0.15)),0,accuracy:0.00001)
  XCTAssertEqual(output(.spring,p,WheelKinematics(position:1)),-0.2,accuracy:0.00001)
  XCTAssertEqual(output(.spring,p,WheelKinematics(position:-1)),0.1,accuracy:0.00001)
 }
 func testPositiveFrictionAndDamperNeverAssistMotion(){
  for kind:BridgeEffect.Kind in [.friction,.damper] {
   for v in [-2.0,-0.3,-0.01,0,0.01,0.3,2] {
    let f=output(kind,[0,6000,6000,10000,10000,0],WheelKinematics(velocity:v))
    XCTAssertLessThanOrEqual(f*v,0)
    // Measured motor sign -1 must also preserve the canonical physical torque.
    let motorCodeForce=f * -1;let measuredTorque=motorCodeForce * -1
    XCTAssertLessThanOrEqual(measuredTorque*v,0)
   }
  }
 }
 func testGameAndDeviceGainsAreNotMultipliedByHiddenQuarter(){
  var s=BridgeForceState();s.deviceGain=8000;s.effects=[BridgeEffect(slot:0,kind:.constant,gain:5000,params:[10000])]
  XCTAssertEqual(EffectEngine().force(s,wheel:WheelKinematics(),now:1),-0.4,accuracy:0.00001)
 }
}
