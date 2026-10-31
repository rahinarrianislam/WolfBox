import Foundation

public struct User: Codable, Identifiable, Sendable {
    public var id: String
    public var email: String?
    public var name: String?
    public var role: String?
    public var box_id: String?
    public var backend: String?
    public var created_at: String?
}
public struct AuthResponse: Codable, Sendable { public var token: String?; public var user: User }
public struct LLM: Codable, Sendable {
    public var active_backend: String?; public var backend: String?; public var model: String?
    public var caption: String {
        switch active_backend ?? backend {
        case "gemini", "openrouter": return "Gemma 4 · cloud"
        case "ollama": return "Gemma 4 · local (offline)"
        case "fake": return "Gemma 4 · fake"
        default: return "Gemma 4 · unavailable"
        }
    }
}
public struct Failure: Codable, Sendable { public var test: String?; public var message: String? }
public struct RelatedRun: Codable, Sendable { public var run_id: String?; public var assignment: String?; public var tag: String? }
public struct Run: Codable, Identifiable, Sendable {
    public var run_id: String?
    public var ts: String?; public var assignment: String?; public var status: String?
    public var passed: [String]?; public var failed: [Failure]?; public var duration_ms: Double?
    public var tags: [String]?; public var hint: String?; public var hint_status: String?
    public var related_past: [RelatedRun]?; public var llm: LLM?
    public var id: String { run_id ?? "unknown" }
    public var isComplete: Bool { status != nil && status != "running" && hint_status != "pending" }
}
public struct Profile: Codable, Sendable { public var mistake_counts: [String: Int]? }
public struct Nudge: Codable, Sendable { public var active: Bool?; public var reason: String?; public var draft: String? }
public struct StudentState: Codable, Sendable {
    public var student_id: String?; public var name: String?; public var assignment: String?; public var code: String?
    public var profile: Profile?; public var nudge: Nudge?; public var llm: LLM?; public var last_run: Run?
}
public struct Assignment: Codable, Identifiable, Sendable {
    public var id: String; public var title: String?; public var due: String?; public var has_tests: Bool?
}
public struct Doc: Codable, Identifiable, Sendable {
    public var doc_id: String; public var title: String?; public var type: String?; public var version: Int?
    public var summary: String?; public var change_note: String?; public var fetched_at: String?
    public var id: String { doc_id }
}
public struct DocResponse: Codable, Sendable { public var doc: Doc?; public var text: String?; public init(doc: Doc?, text: String?) { self.doc = doc; self.text = text } }
public struct Deadline: Codable, Sendable { public var what: String?; public var due: String?; public var source_doc: String? }
public struct SyncIssue: Codable, Sendable { public var item: String?; public var error: String? }
public struct SyncJob: Codable, Sendable {
    public var job_id: String?; public var status: String?; public var new: [String]?; public var changed: [String]?
    public var unchanged: Int?; public var errors: [SyncIssue]?
}
public struct Rating: Codable, Sendable {
    public var rating: Double?; public var source: String?; public var url: String?
    public init(from decoder: Decoder) throws {
        if let value = try? decoder.singleValueContainer().decode(Double.self) { rating = value; source = nil; url = nil; return }
        let c = try decoder.container(keyedBy: CodingKeys.self)
        rating = try c.decodeIfPresent(Double.self, forKey: .rating)
        source = try c.decodeIfPresent(String.self, forKey: .source)
        url = try c.decodeIfPresent(String.self, forKey: .url)
    }
}
public struct Seats: Codable, Sendable { public var open: Int?; public var capacity: Int? }
public struct CourseSection: Codable, Sendable {
    public var course: String?; public var section_id: String?; public var days: [String]?
    public var start: String?; public var end: String?; public var instructor: String?; public var rating: Rating?; public var seats: Seats?
}
public struct ScheduleOption: Codable, Sendable {
    public var sections: [CourseSection]?; public var credits: Int?; public var avg_rating: Double?
    public var explanation: String?; public var score: Double?
}
public struct Requirement: Codable, Sendable {
    public var id: String?; public var name: String?; public var remaining: Int?; public var courses_needed: Int?
    public var options: [String]?
}
public struct Catalog: Codable, Sendable {
    public var sample: Bool?; public var term: String?; public var fetched_at: String?
    public var caption: String {
        if sample == false { return "Live NC State class schedule · \(term ?? "Unknown term") · updated \(fetched_at ?? "unknown time")" }
        return "Sample data"
    }
}
public struct SavedPlan: Codable, Sendable { public var prefs_text: String?; public var last_options: [ScheduleOption]?; public var catalog: Catalog? }
public struct PlanResponse: Codable, Sendable {
    public var plan: SavedPlan?; public var options: [ScheduleOption]?; public var remaining: [Requirement]?; public var catalog: Catalog?
}
public struct Heatmap: Codable, Sendable {
    public var students: Int?; public var mistake_tags: [String: Int]?; public var failing_tests: [String: Int]?
    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        students = (try? c.decode(Int.self, forKey: .students)) ?? (try? c.decode([JSONValue].self, forKey: .students).count)
        mistake_tags = try c.decodeIfPresent([String: Int].self, forKey: .mistake_tags)
        failing_tests = try c.decodeIfPresent([String: Int].self, forKey: .failing_tests)
    }
}
public struct TextResponse: Codable, Sendable { public var echo: String?; public var reply: String?; public var markdown: String?; public var summary: String? }
public struct ListResponse: Codable, Sendable {
    public var assignments: [Assignment]?; public var docs: [Doc]?; public var deadlines: [Deadline]?; public var runs: [Run]?
}
public struct JobResponse: Codable, Sendable { public var run_id: String?; public var job_id: String?; public var task_id: String? }
public struct RunResponse: Codable, Sendable { public var run: Run? }
public struct SyncResponse: Codable, Sendable { public var job: SyncJob? }
public struct EmptyResponse: Codable, Sendable {}

/// JSON values retain evolving delegation step/result payloads without assuming one provider's format.
public enum JSONValue: Codable, Sendable, CustomStringConvertible {
    case string(String), number(Double), bool(Bool), array([JSONValue]), object([String: JSONValue]), null
    public init(from decoder: Decoder) throws {
        let c = try decoder.singleValueContainer()
        if c.decodeNil() { self = .null }
        else if let v = try? c.decode(String.self) { self = .string(v) }
        else if let v = try? c.decode(Bool.self) { self = .bool(v) }
        else if let v = try? c.decode(Double.self) { self = .number(v) }
        else if let v = try? c.decode([JSONValue].self) { self = .array(v) }
        else { self = .object(try c.decode([String: JSONValue].self)) }
    }
    public func encode(to encoder: Encoder) throws {
        var c = encoder.singleValueContainer()
        switch self {
        case .string(let v): try c.encode(v)
        case .number(let v): try c.encode(v)
        case .bool(let v): try c.encode(v)
        case .array(let v): try c.encode(v)
        case .object(let v): try c.encode(v)
        case .null: try c.encodeNil()
        }
    }
    public var description: String {
        switch self {
        case .string(let v): return v
        case .number(let v): return String(v)
        case .bool(let v): return String(v)
        case .array(let v): return v.map(\.description).joined(separator: "\n")
        case .object(let v): return v.keys.sorted().map { "\($0): \(v[$0]!.description)" }.joined(separator: "\n")
        case .null: return ""
        }
    }
}
public struct DelegateTask: Codable, Sendable {
    public var task_id: String?; public var status: String?; public var steps: [JSONValue]?
    public var result: JSONValue?; public var watch_url: String?; public var takeover_url: String?; public var error: String?; public var mode: String?
    public var isTerminal: Bool { ["completed", "done", "succeeded", "failed", "error", "cancelled", "denied"].contains(status ?? "") }
}
public struct MoodleAuthorization: Sendable {
    public var authorized: Bool; public var role: String
    public init(authorized: Bool, role: String) { self.authorized = authorized; self.role = role }
    public func allows(_ kind: String) -> Bool {
        guard authorized, role == "instructor" else { return false }
        switch kind {
        case "open_course", "list_assignments": return true
        case "publish_assignment": return role == "instructor"
        default: return false
        }
    }
}

public struct WeekLayout {
    public struct Meeting: Identifiable {
        public var id: String; public var day: String; public var start: Int; public var end: Int; public var section: CourseSection
    }
    public var meetings: [Meeting]
    public var startMinute: Int; public var endMinute: Int
    public static func minutes(_ time: String) -> Int? {
        let parts = time.split(separator: ":").compactMap { Int($0) }
        guard parts.count == 2, (0...23).contains(parts[0]), (0...59).contains(parts[1]) else { return nil }
        return parts[0] * 60 + parts[1]
    }
    public init(sections: [CourseSection]) {
        meetings = sections.enumerated().flatMap { index, section -> [Meeting] in
            guard let start = Self.minutes(section.start ?? ""), let end = Self.minutes(section.end ?? ""), end > start else { return [] }
            return (section.days ?? []).map { Meeting(id: "\(index)-\($0)", day: String($0.prefix(3)), start: start, end: end, section: section) }
        }
        startMinute = min(8 * 60, (meetings.map(\.start).min() ?? 480) / 60 * 60)
        endMinute = max(17 * 60, ((meetings.map(\.end).max() ?? 1020) + 59) / 60 * 60)
    }
}
