import XCTest
@testable import WolfBoxCore

final class StubProtocol: URLProtocol, @unchecked Sendable {
    static var handler: ((URLRequest) throws -> (Int, Data))?
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        do {
            let (status, data) = try Self.handler!(request)
            let response = HTTPURLResponse(url: request.url!, statusCode: status, httpVersion: nil, headerFields: ["Content-Type": "application/json"])!
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: data)
            client?.urlProtocolDidFinishLoading(self)
        } catch { client?.urlProtocol(self, didFailWithError: error) }
    }
    override func stopLoading() {}
}
final class APITests: XCTestCase {
    var api: APIClient!
    override func setUp() {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [StubProtocol.self]
        api = APIClient(baseURL: "http://localhost:8000", token: "test-session", session: URLSession(configuration: configuration))
    }
    override func tearDown() { api.session.invalidateAndCancel(); StubProtocol.handler = nil }
    func testBearerAndBodySent() async throws {
        StubProtocol.handler = { request in
            XCTAssertEqual(request.value(forHTTPHeaderField: "Authorization"), "Bearer test-session")
            XCTAssertEqual(request.httpMethod, "POST")
            XCTAssertEqual(request.url?.path, "/api/students/alex/submit")
            return (200, Data(#"{"run_id":"r_live","extra":"ignored"}"#.utf8))
        }
        let result = try await api.request(JobResponse.self, ["api","students","alex","submit"], method: "POST", body: ["code": .string("print(1)"), "assignment": .string("hw4")])
        XCTAssertEqual(result.run_id, "r_live")
    }
    func testUnauthorizedIsDistinctFromOfflineFailure() async throws {
        StubProtocol.handler = { _ in (401, Data(#"{"error":"Invalid token"}"#.utf8)) }
        do { let _ = try await api.request(EmptyResponse.self, ["api","auth","me"]); XCTFail("401 must throw") }
        catch APIError.unauthorized {} catch { XCTFail("Unexpected: \(error)") }
        StubProtocol.handler = { _ in throw URLError(.cannotConnectToHost) }
        do { let _ = try await api.request(EmptyResponse.self, ["api","auth","me"]); XCTFail("offline must throw") }
        catch let error as URLError { XCTAssertEqual(error.code, .cannotConnectToHost) }
    }
    func testServerErrorAndMalformedResponseStayRecoverable() async throws {
        StubProtocol.handler = { _ in (409, Data(#"{"error":"Email already exists"}"#.utf8)) }
        do { let _ = try await api.request(AuthResponse.self, ["api","auth","signup"]); XCTFail("409 must throw") }
        catch APIError.server(let status, let text) { XCTAssertEqual(status, 409); XCTAssertEqual(text, "Email already exists") }
        StubProtocol.handler = { _ in (200, Data("not JSON".utf8)) }
        do { let _ = try await api.request(AuthResponse.self, ["api","auth","login"]); XCTFail("bad JSON must throw") }
        catch APIError.invalidResponse {}
    }
    func testNumericAndObjectRatingsDecode() throws {
        let input = Data(#"[{"course":"A","rating":4.2},{"course":"B","rating":{"rating":4.5,"source":"rmp","url":"https://www.ratemyprofessors.com/professor/1"}},{"course":"C"}]"#.utf8)
        let result = try JSONDecoder().decode([CourseSection].self, from: input)
        XCTAssertEqual(result[0].rating?.rating, 4.2)
        XCTAssertEqual(result[1].rating?.source, "rmp")
        XCTAssertNil(result[2].rating)
    }
    func testDelegateStepShapesDecodeWithoutLosingResult() throws {
        let task = try JSONDecoder().decode(DelegateTask.self, from: Data(#"{"task_id":"t","status":"needs_human","steps":["Opened",{"description":"Awaiting sign-in","status":"waiting"}],"result":{"count":3},"takeover_url":"https://example.test/task"}"#.utf8))
        XCTAssertEqual(task.steps?.count, 2)
        XCTAssertFalse(task.isTerminal)
        XCTAssertEqual(task.result?.description, "count: 3.0")
    }
}
