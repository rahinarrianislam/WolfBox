import XCTest
@testable import WolfBox
import WolfBoxCore

private final class OfflineProtocol: URLProtocol, @unchecked Sendable {
    static var status = 0
    static var count = 0
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        Self.count += 1
        if Self.status == 401 {
            let response = HTTPURLResponse(url: request.url!, statusCode: 401, httpVersion: nil, headerFields: nil)!
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: Data(#"{"error":"Expired"}"#.utf8))
            client?.urlProtocolDidFinishLoading(self)
        } else { client?.urlProtocol(self, didFailWithError: URLError(.cannotConnectToHost)) }
    }
    override func stopLoading() {}
}
@MainActor final class AppModelTests: XCTestCase {
    func model() -> AppModel {
        let model = AppModel(fixtures: true)
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [OfflineProtocol.self]
        model.urlSession = URLSession(configuration: config)
        model.serverURL = "http://wolfbox-unit-tests.invalid"
        OfflineProtocol.count = 0; OfflineProtocol.status = 0
        return model
    }
    func testOfflineFailurePreservesDraftAndSession() async {
        let model = model()
        model.fixtures = false; model.editCode("# unsaved work")
        await model.loadStudent()
        XCTAssertEqual(model.code, "# unsaved work")
        XCTAssertEqual(model.user?.id, "alex")
        XCTAssertNotNil(model.error)
        XCTAssertFalse(model.busy.contains("student"))
    }
    func test401ReturnsToSignInAndClearsStudentData() async {
        let model = model()
        model.fixtures = false; OfflineProtocol.status = 401
        await model.loadPlan()
        XCTAssertNil(model.user)
        XCTAssertNil(model.state)
        XCTAssertNil(model.plan)
        XCTAssertTrue(model.busy.isEmpty)
        XCTAssertNotNil(model.error)
    }
    func testMoodleRejectsNonInstructorWithoutAnyRequest() async {
        let model = model()
        model.fixtures = false; model.moodleAuthorized = true
        await model.startMoodle("list_assignments")
        XCTAssertEqual(OfflineProtocol.count, 0)
        XCTAssertNotNil(model.error)
        XCTAssertFalse(model.destinations.contains(.moodle))
    }
    func testFixtureScreensAndFakeMoodleAreComplete() async {
        let model = model()
        XCTAssertEqual(model.plan?.options?.count, 3)
        XCTAssertFalse(model.docs.isEmpty)
        XCTAssertNotNil(model.state?.nudge?.draft)
        model.loadFixtures(role: "ta")
        XCTAssertFalse(model.summary.isEmpty)
        XCTAssertFalse(model.runs.isEmpty)
        model.loadFixtures(role: "instructor")
        XCTAssertTrue(model.destinations.contains(.moodle))
        XCTAssertEqual(model.delegateTask?.mode, "fake")
        XCTAssertEqual(model.moodleCourse, "csc116")
        XCTAssertEqual(model.moodleAssignment, "hw5")
        XCTAssertFalse(model.moodleAuthorized)
        XCTAssertEqual(OfflineProtocol.count, 0)
    }
}
