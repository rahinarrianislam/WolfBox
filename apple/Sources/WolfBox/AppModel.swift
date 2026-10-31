import Foundation
import Observation
import WolfBoxCore

struct Fixtures: Decodable {
    var user: User; var students: [User]; var state: StudentState; var assignments: [Assignment]
    var docs: [Doc]; var document: DocResponse; var deadlines: [Deadline]; var plan: PlanResponse
    var runs: [Run]; var summary: TextResponse; var heatmap: Heatmap; var sync: SyncJob; var delegation: DelegateTask
    static func load() -> Fixtures {
        // Bundled fixtures are a build-time contract, never a substitute for a failed live request.
        let url = Bundle.module.url(forResource: "demo", withExtension: "json")!
        return try! JSONDecoder().decode(Fixtures.self, from: Data(contentsOf: url))
    }
}

enum Destination: String, CaseIterable, Identifiable {
    case learn = "Learn", course = "Course", plan = "Plan", ta = "TA handoff", instructor = "Instructor", canvas = "Canvas tasks"
    var id: String { rawValue }
    var symbol: String {
        switch self {
        case .learn: return "curlybraces"
        case .course: return "books.vertical"
        case .plan: return "calendar"
        case .ta: return "person.2"
        case .instructor: return "chart.bar.xaxis"
        case .canvas: return "arrow.up.forward.app"
        }
    }
}

@MainActor @Observable
final class AppModel {
    var serverURL = UserDefaults.standard.string(forKey: "serverURL") ?? "http://127.0.0.1:8000"
    var user: User?
    var destination: Destination = .learn
    var fixtures: Bool
    var error: String?
    var notice: String?
    var busy: Set<String> = []
    var state: StudentState?
    var assignments: [Assignment] = []
    var assignment = "hw4"
    var code = ""
    var run: Run?
    var runTimedOut = false
    var question = ""
    var answer = ""
    var docs: [Doc] = []
    var document: DocResponse?
    var deadlines: [Deadline] = []
    var syncJob: SyncJob?
    var prefs = ""
    var echo = ""
    var plan: PlanResponse?
    var optionIndex = 0
    var students: [User] = []
    var selectedStudent = ""
    var studentStates: [String: StudentState] = [:]
    var summary = ""
    var runs: [Run] = []
    var heatmap: Heatmap?
    var canvasCourses: [CanvasCourse] = []
    var selectedCanvasCourse = ""
    var canvasAuthorized = false
    var canvasCourse = "csc116"
    var canvasAssignment = "hw5"
    var delegateTask: DelegateTask?
    var delegateTasks: [DelegateTask] = []
    var urlSession: URLSession = .shared
    var delegateTimedOut = false
    private var token: String?
    private var generation = UUID()
    private var drafts: [String: String] = [:]
    private let keychain = KeychainStore()
    private var fixtureData: Fixtures?

    init(fixtures: Bool = ProcessInfo.processInfo.arguments.contains("--demo-fixtures")) {
        self.fixtures = fixtures
        if fixtures { loadFixtures() }
    }
    var destinations: [Destination] {
        switch user?.role {
        case "ta": return [.ta]
        case "instructor": return [.instructor, .canvas]
        default: return [.learn, .course, .plan]
        }
    }
    var studentPath: [String] { ["api", "students", user?.id ?? ""] }
    var client: APIClient { APIClient(baseURL: serverURL, token: token, session: urlSession) }
    var isRunning: Bool { busy.contains("run") }

    func loadFixtures(role: String = "student") {
        let f = Fixtures.load(); fixtureData = f
        user = f.user; user?.role = role
        if role == "ta" { user?.name = "Jordan Lee"; destination = .ta }
        else if role == "instructor" { user?.name = "Dr. Morgan"; destination = .instructor }
        else { destination = .learn }
        state = f.state; code = f.state.code ?? ""; run = f.state.last_run
        canvasCourses = [CanvasCourse(id: "116", name: "Sample · CSC 116")]; selectedCanvasCourse = "116"
        assignments = f.assignments; docs = f.docs; document = nil; deadlines = f.deadlines
        plan = f.plan; prefs = f.plan.plan?.prefs_text ?? ""; echo = "Start at 9 AM or later. Keep Tuesday and Thursday afternoons free. 12–15 credits."
        students = f.students; selectedStudent = f.students.first?.id ?? ""
        studentStates = ["alex": f.state]
        summary = f.summary.markdown ?? ""; runs = f.runs; heatmap = f.heatmap; syncJob = f.sync
        delegateTask = f.delegation; delegateTasks = [f.delegation]; canvasCourse = "csc116"; canvasAssignment = "hw5"; canvasAuthorized = false; optionIndex = 0
    }
    func perform(_ key: String, _ work: () async throws -> Void) async {
        guard !busy.contains(key) else { return }
        let version = generation
        busy.insert(key); error = nil
        defer { if generation == version { busy.remove(key) } }
        do { try await work() }
        catch is CancellationError {}
        catch {
            guard generation == version else { return }
            if case APIError.unauthorized = error { endSession(); self.error = error.localizedDescription }
            else if (error as? URLError)?.code != .cancelled { self.error = error.localizedDescription }
        }
    }
    func request<T: Decodable & Sendable>(_ type: T.Type, _ path: [String], method: String = "GET", body: [String: JSONValue]? = nil, query: [String: String] = [:], timeout: TimeInterval = 30) async throws -> T {
        let version = generation
        let value = try await client.request(type, path, method: method, body: body, query: query, timeout: timeout)
        guard version == generation else { throw CancellationError() }
        try Task.checkCancellation()
        return value
    }
    func restoreSession() async {
        guard !fixtures, user == nil else { return }
        token = keychain.read(server: serverURL)
        guard token != nil else { return }
        await perform("auth") {
            let response = try await request(AuthResponse.self, ["api", "auth", "me"])
            user = response.user; destination = destinations.first ?? .learn
        }
    }
    func authenticate(email: String, password: String, name: String, role: String, signup: Bool) async {
        guard !fixtures else { return }
        await perform("auth") {
            var body: [String: JSONValue] = ["email": .string(email.trimmingCharacters(in: .whitespacesAndNewlines)), "password": .string(password)]
            if signup { body["name"] = .string(name); body["role"] = .string(role) }
            let response = try await request(AuthResponse.self, ["api", "auth", signup ? "signup" : "login"], method: "POST", body: body, timeout: 90)
            guard let saved = response.token, !saved.isEmpty else { throw APIError.invalidResponse }
            try keychain.save(saved, server: serverURL)
            token = saved; user = response.user; destination = destinations.first ?? .learn
        }
    }
    func endSession() {
        generation = UUID(); if !fixtures { keychain.delete(server: serverURL) }; token = nil; user = nil
        state = nil; run = nil; code = ""; drafts = [:]; assignments = []; docs = []; deadlines = []
        plan = nil; students = []; studentStates = [:]; summary = ""; runs = []; heatmap = nil
        delegateTask = nil; delegateTasks = []; canvasCourses = []; selectedCanvasCourse = ""; canvasAuthorized = false; busy = []; answer = ""; document = nil; syncJob = nil
        prefs = ""; echo = ""; question = ""; selectedStudent = ""; optionIndex = 0
        assignment = "hw4"; runTimedOut = false; delegateTimedOut = false; notice = nil; error = nil
        canvasCourse = "csc116"; canvasAssignment = "hw5"
    }
    func logout() async {
        if fixtures { endSession(); fixtures = false; return }
        if !fixtures { await perform("logout") { let _: EmptyResponse = try await request(EmptyResponse.self, ["api", "auth", "logout"], method: "POST", body: [:]) } }
        endSession()
    }
    func changeServer(_ value: String) throws {
        _ = try APIClient.makeURL(base: value, segments: [])
        if value != serverURL || fixtures {
            endSession(); fixtures = false; serverURL = value.trimmingCharacters(in: .whitespacesAndNewlines)
            UserDefaults.standard.set(serverURL, forKey: "serverURL")
        }
    }
    func loadDestination() async {
        if fixtures { return }
        switch destination {
        case .learn: await loadStudent(); await loadAssignments()
        case .course: await loadCourse()
        case .plan: await loadPlan()
        case .ta: await loadRoster()
        case .instructor: await loadHeatmap()
        case .canvas: await loadCanvasCourses(); await loadCanvasTasks()
        }
    }
    func loadStudent() async {
        let target = assignment
        await perform("student") {
            let result = try await request(StudentState.self, studentPath + ["state"], query: ["assignment": target])
            guard assignment == target else { return }
            state = result; run = result.last_run
            code = drafts[target] ?? result.code ?? ""
        }
    }
    func editCode(_ value: String) { code = value; drafts[assignment] = value }
    func selectAssignment(_ target: String) async {
        drafts[assignment] = code; assignment = target; run = nil; runTimedOut = false
        if fixtures { code = drafts[target] ?? (target == "hw4" ? fixtureData?.state.code ?? "" : "# \(target)\n# Start your work here.\n"); return }
        code = drafts[target] ?? ""
        await loadStudent()
    }
    func loadAssignments() async {
        await perform("assignments") { assignments = try await request(ListResponse.self, studentPath + ["assignments"]).assignments ?? [] }
    }
    func runTests() async {
        runTimedOut = false
        if fixtures { run = fixtureData?.state.last_run; notice = "Fixture run shown. No code was executed."; return }
        let target = assignment; let path = studentPath
        await perform("run") {
            let job = try await request(JobResponse.self, path + ["submit"], method: "POST", body: ["code": .string(code), "assignment": .string(target)])
            guard let id = job.run_id else { throw APIError.invalidResponse }
            let deadline = Date().addingTimeInterval(75)
            while Date() < deadline {
                let remaining = deadline.timeIntervalSinceNow
                let value: RunResponse
                do { value = try await request(RunResponse.self, path + ["runs", id], timeout: max(0.1, min(10, remaining))) }
                catch let failure as URLError where failure.code != .cancelled {
                    if Date() >= deadline { break }
                    try await Task.sleep(for: .seconds(min(1, deadline.timeIntervalSinceNow)))
                    continue
                }
                guard target == assignment else { throw CancellationError() }
                guard let latest = value.run else { throw APIError.invalidResponse }
                run = latest
                if latest.isComplete { await loadStudent(); return }
                try await Task.sleep(for: .seconds(min(1, max(0, deadline.timeIntervalSinceNow))))
            }
            runTimedOut = true; throw APIError.timedOut
        }
    }
    func askTutor() async {
        let text = question.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }
        await perform("ask") {
            if fixtures { answer = "Think about the final position in the list. How many indices does range(len(xs) - 1) actually visit?"; return }
            answer = try await request(TextResponse.self, studentPath + ["ask"], method: "POST", body: ["text": .string(text)]).reply ?? "The tutor returned no answer. Try a more specific question."
        }
    }
    func loadCanvasCourses() async {
        if fixtures {
            canvasCourses = [CanvasCourse(id: "116", name: "Sample · CSC 116")]
            selectedCanvasCourse = "116"
            return
        }
        await perform("canvas-courses") {
            let path = user?.role == "instructor" ? ["api", "delegate", "canvas", "courses"] : studentPath + ["canvas", "courses"]
            let response = try await request(CanvasCoursesResponse.self, path)
            canvasCourses = response.courses
            if selectedCanvasCourse.isEmpty { selectedCanvasCourse = response.selected_course_id ?? "" }
        }
    }
    func loadCourse() async {
        await loadCanvasCourses()
        await perform("docs") { docs = try await request(ListResponse.self, studentPath + ["docs"]).docs ?? [] }
        await perform("deadlines") { deadlines = try await request(ListResponse.self, studentPath + ["deadlines"]).deadlines ?? [] }
    }
    func readDoc(_ doc: Doc) async {
        await perform("document") {
            if fixtures { document = DocResponse(doc: doc, text: fixtureData?.document.text); return }
            document = try await request(DocResponse.self, studentPath + ["docs", doc.doc_id])
        }
    }
    func syncCourse() async {
        if fixtures { syncJob = fixtureData?.sync; notice = "Fixture sync shown. The course site was not contacted."; return }
        await perform("sync") {
            guard !selectedCanvasCourse.isEmpty else { throw APIError.server(400, "Choose a Canvas course first.") }
            let job = try await request(JobResponse.self, studentPath + ["sync"], method: "POST", body: ["canvas_course_id": .string(selectedCanvasCourse)])
            guard let id = job.job_id else { throw APIError.invalidResponse }
            let deadline = Date().addingTimeInterval(75)
            while Date() < deadline {
                let value = try await request(SyncResponse.self, studentPath + ["sync", id], timeout: max(0.1, min(10, deadline.timeIntervalSinceNow)))
                syncJob = value.job
                if let status = value.job?.status, status != "running" {
                    await loadCourse(); await loadAssignments()
                    if status == "error" { throw APIError.server(502, "Course sync failed. Check the item errors below.") }
                    return
                }
                try await Task.sleep(for: .seconds(1))
            }
            throw APIError.timedOut
        }
    }
    func loadPlan() async {
        await perform("plan") {
            plan = try await request(PlanResponse.self, studentPath + ["plan"])
            prefs = plan?.plan?.prefs_text ?? prefs; optionIndex = 0
        }
    }
    func savePrefs() async {
        await perform("prefs") {
            if fixtures { echo = "Start at 9 AM or later. Keep Tuesday and Thursday afternoons free. 12–15 credits. (Fixture)"; return }
            echo = try await request(TextResponse.self, studentPath + ["plan", "prefs"], method: "POST", body: ["text": .string(prefs)]).echo ?? "Preferences saved."
        }
    }
    func solvePlan() async {
        await perform("solve") {
            if fixtures { plan = fixtureData?.plan; optionIndex = 0; notice = "Fixture schedules shown. No solver was run."; return }
            let result = try await request(PlanResponse.self, studentPath + ["plan", "solve"], method: "POST", body: [:])
            if plan == nil { plan = result } else { plan?.options = result.options; plan?.catalog = result.catalog }; optionIndex = 0
        }
    }
    func loadRoster() async {
        await perform("roster") {
            students = try await request([User].self, ["api", "students"])
            for student in students {
                do { studentStates[student.id] = try await request(StudentState.self, ["api", "students", student.id, "state"]) }
                catch APIError.unauthorized { throw APIError.unauthorized }
                catch { studentStates.removeValue(forKey: student.id) }
            }
        }
        if selectedStudent.isEmpty { selectedStudent = students.first?.id ?? "" }
        if !selectedStudent.isEmpty { await selectStudent(selectedStudent) }
    }
    func selectStudent(_ id: String) async {
        selectedStudent = id; summary = ""; runs = []
        if fixtures { summary = id == "alex" ? fixtureData?.summary.markdown ?? "" : "**Sam Chen** has no prior run history. Begin with the current test failure and ask what they expected."; runs = id == "alex" ? fixtureData?.runs ?? [] : []; return }
        await perform("handoff") {
            let result = try await request(TextResponse.self, ["api", "students", id, "ta-summary"])
            guard selectedStudent == id else { return }
            summary = result.markdown ?? result.summary ?? "No handoff available."
            let history = try await request(ListResponse.self, ["api", "students", id, "runs"])
            guard selectedStudent == id else { return }
            runs = history.runs ?? []
        }
    }
    func loadHeatmap() async {
        await perform("heatmap") { heatmap = try await request(Heatmap.self, ["api", "instructor", "heatmap"]) }
    }
    func publish(_ item: String) async {
        await perform("publish") {
            if fixtures { notice = "Fixture mode: \(item) was not published."; return }
            let _: EmptyResponse = try await request(EmptyResponse.self, ["api", "instructor", "publish"], method: "POST", body: ["item": .string(item)])
            notice = "\(item == "hw5" ? "HW5 published" : "HW4 specification updated"). Student boxes will see it on their next sync."
        }
    }
    func resetCourse() async {
        await perform("publish") {
            if fixtures { notice = "Fixture mode: course was not reset."; return }
            let _: EmptyResponse = try await request(EmptyResponse.self, ["api", "instructor", "reset-course"], method: "POST", body: [:])
            notice = "Course manifest restored to its initial state."
        }
    }
    func startCanvas(_ kind: String) async {
        guard CanvasAuthorization(authorized: canvasAuthorized, role: user?.role ?? "").allows(kind), !canvasCourse.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            error = "Canvas tasks require an instructor account and your authorization for this course."; return
        }
        if kind == "publish_assignment", canvasAssignment.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty { error = "Enter the staged assignment ID to publish first."; return }
        delegateTimedOut = false
        await perform("canvas") {
            if fixtures { delegateTask = fixtureData?.delegation; notice = "Fixture task shown. Canvas was not contacted."; return }
            guard token != nil else { throw APIError.unauthorized }
            guard !selectedCanvasCourse.isEmpty else { throw APIError.server(400, "Choose a Canvas course first.") }
            var body: [String: JSONValue] = ["course": .string("canvas-" + selectedCanvasCourse), "canvas_course_id": .string(selectedCanvasCourse)]
            if kind == "publish_assignment" { body["item"] = .string(canvasAssignment.trimmingCharacters(in: .whitespacesAndNewlines)) }
            let job = try await request(JobResponse.self, ["api", "delegate", "canvas", kind], method: "POST", body: body)
            guard let id = job.task_id else { throw APIError.invalidResponse }
            try await pollCanvas(id)
            await loadCanvasTasks()
        }
    }
    func pollCanvas(_ id: String) async throws {
        let deadline = Date().addingTimeInterval(75)
        while Date() < deadline {
            delegateTask = try await request(DelegateTask.self, ["api", "delegate", "tasks", id], timeout: max(0.1, min(10, deadline.timeIntervalSinceNow)))
            if delegateTask?.isTerminal == true { return }
            if ["awaiting_authorization", "awaiting_login", "needs_takeover", "waiting_for_user", "needs_human"].contains(delegateTask?.status ?? "") { return }
            try await Task.sleep(for: .seconds(1))
        }
        delegateTimedOut = true; throw APIError.timedOut
    }
    func loadCanvasTasks() async {
        guard user?.role == "instructor" else { error = "Canvas tasks require an instructor account."; return }
        if fixtures { return }
        await perform("canvas-history") { delegateTasks = try await request([DelegateTask].self, ["api", "delegate", "tasks"]) }
    }
    func openCanvasTask(_ task: DelegateTask) async {
        guard user?.role == "instructor" else { return }
        delegateTask = task
        await refreshCanvas()
    }
    func refreshCanvas() async {
        guard !fixtures, user?.role == "instructor", let id = delegateTask?.task_id, token != nil else { return }
        await perform("canvas") { try await pollCanvas(id) }
    }
}
