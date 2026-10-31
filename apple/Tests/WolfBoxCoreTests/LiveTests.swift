import XCTest
@testable import WolfBoxCore

final class LiveTests: XCTestCase {
    func testLocalDemoContracts() async throws {
        guard let base = ProcessInfo.processInfo.environment["WOLFBOX_LIVE_URL"] else { throw XCTSkip("Run apple/scripts/live-check.sh for the isolated live backend test.") }
        // This checkout predates auth. The app never offers an unauthenticated live session.
        let api = APIClient(baseURL: base, token: "native-contract-check")
        let _: EmptyResponse = try await api.request(EmptyResponse.self, ["api","health"])
        do {
            let _ = try await api.request(AuthResponse.self, ["api","auth","me"])
            print("Auth endpoint is available; run the signed-in UI integration separately.")
        } catch APIError.server(let status, _) {
            XCTAssertEqual(status, 404)
            print("LIVE: auth/me unavailable (404); auth UI remains fixture/transport-tested only.")
        }
        let _: EmptyResponse = try await api.request(EmptyResponse.self, ["api","students"], method: "POST", body: ["id":.string("alex"),"name":.string("Alex Rivera")])
        let p = ["api","students","alex"]
        let state = try await api.request(StudentState.self, p + ["state"])
        XCTAssertEqual(state.student_id, "alex")
        XCTAssertEqual(state.llm?.active_backend, "fake")
        let assignments = try await api.request(ListResponse.self, p + ["assignments"])
        XCTAssertTrue(assignments.assignments?.contains { $0.id == "hw4" } == true)
        let submission = try await api.request(JobResponse.self, p + ["submit"], method: "POST", body: ["assignment":.string("hw4"),"code":.string("def sum_list(xs):\n    return sum(xs[:-1])\n\ndef safe_max(xs):\n    return max(xs) if xs else None\n")])
        let id = try XCTUnwrap(submission.run_id)
        var latest: Run?
        for _ in 0..<75 {
            latest = try await api.request(RunResponse.self, p + ["runs",id]).run
            if latest?.isComplete == true { break }
            try await Task.sleep(for: .seconds(1))
        }
        XCTAssertTrue(latest?.isComplete == true)
        XCTAssertFalse(latest?.failed?.isEmpty ?? true)
        let answer = try await api.request(TextResponse.self, p + ["ask"], method: "POST", body: ["text":.string("Why does the last index fail?")])
        XCTAssertFalse(answer.reply?.isEmpty ?? true)
        let handoff = try await api.request(TextResponse.self, p + ["ta-summary"])
        XCTAssertFalse(handoff.markdown?.isEmpty ?? true)
        let history = try await api.request(ListResponse.self, p + ["runs"])
        XCTAssertFalse(history.runs?.isEmpty ?? true)
        for item in ["hw5","hw4-v2"] {
            let _: EmptyResponse = try await api.request(EmptyResponse.self, ["api","instructor","publish"], method:"POST", body:["item":.string(item)])
        }
        let sync = try await api.request(JobResponse.self, p + ["sync"], method:"POST", body:[:])
        var job: SyncJob?
        for _ in 0..<75 {
            job = try await api.request(SyncResponse.self, p + ["sync", try XCTUnwrap(sync.job_id)]).job
            if job?.status != "running" { break }
            try await Task.sleep(for: .seconds(1))
        }
        XCTAssertEqual(job?.status, "done")
        let docs = try await api.request(ListResponse.self, p + ["docs"])
        let doc = try XCTUnwrap(docs.docs?.first { $0.doc_id == "csc116/hw4" })
        let reader = try await api.request(DocResponse.self, p + ["docs",doc.doc_id])
        XCTAssertFalse(reader.text?.isEmpty ?? true)
        let _ = try await api.request(ListResponse.self, p + ["deadlines"])
        let _ = try await api.request(PlanResponse.self, p + ["plan"])
        let prefs = try await api.request(TextResponse.self, p + ["plan","prefs"], method:"POST", body:["text":.string("no 8 AMs, I work Tue/Thu afternoons, 15 credits max")])
        XCTAssertFalse(prefs.echo?.isEmpty ?? true)
        let plan = try await api.request(PlanResponse.self, p + ["plan","solve"], method:"POST", body:[:])
        XCTAssertFalse(plan.options?.isEmpty ?? true)
        XCTAssertTrue(plan.catalog?.sample == true)
        let heatmap = try await api.request(Heatmap.self, ["api","instructor","heatmap"])
        XCTAssertEqual(heatmap.students, 1)
        let _: EmptyResponse = try await api.request(EmptyResponse.self, ["api","instructor","reset-course"], method:"POST", body:[:])
        print("LIVE PASS: state, assignments, submit/poll, tutor, TA summary/history, publish/update, sync/poll, encoded document reader, deadlines, planner prefs/solve, heatmap, reset. GEMMA_BACKEND=fake.")
    }
}
