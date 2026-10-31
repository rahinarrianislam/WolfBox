import Foundation

public enum APIError: LocalizedError {
    case invalidServer, unauthorized, server(Int, String), invalidResponse, timedOut
    public var errorDescription: String? {
        switch self {
        case .invalidServer: return "Enter a valid http or https server URL without a username or password."
        case .unauthorized: return "Your session ended. Sign in again to continue."
        case .server(let status, let message): return "\(message) (\(status))"
        case .invalidResponse: return "The server returned an unreadable response. Your work is still here."
        case .timedOut: return "This took longer than 75 seconds. The server may still be working. Refresh to check again."
        }
    }
}
public struct APIClient: Sendable {
    public var baseURL: String
    public var token: String?
    public var session: URLSession
    public init(baseURL: String, token: String? = nil, session: URLSession = .shared) {
        self.baseURL = baseURL; self.token = token; self.session = session
    }
    public static func makeURL(base: String, segments: [String], query: [String: String] = [:]) throws -> URL {
        guard var c = URLComponents(string: base.trimmingCharacters(in: .whitespacesAndNewlines)),
              ["http", "https"].contains(c.scheme?.lowercased() ?? ""), c.host?.isEmpty == false,
              c.user == nil, c.password == nil, c.query == nil, c.fragment == nil else { throw APIError.invalidServer }
        let allowed = CharacterSet.alphanumerics.union(CharacterSet(charactersIn: "-._~"))
        c.percentEncodedPath = c.percentEncodedPath.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
            .split(separator: "/").map(String.init).reduce("") { $0 + "/" + $1 }
            + segments.map { "/" + ($0.addingPercentEncoding(withAllowedCharacters: allowed) ?? "") }.joined()
        if !query.isEmpty { c.queryItems = query.keys.sorted().map { URLQueryItem(name: $0, value: query[$0]) } }
        guard let url = c.url else { throw APIError.invalidServer }
        return url
    }
    public func request<T: Decodable & Sendable>(_ type: T.Type, _ segments: [String], method: String = "GET", body: [String: JSONValue]? = nil, query: [String: String] = [:], timeout: TimeInterval = 30) async throws -> T {
        var request = URLRequest(url: try Self.makeURL(base: baseURL, segments: segments, query: query))
        request.httpMethod = method
        request.timeoutInterval = timeout
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        if let token { request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization") }
        if let body { request.httpBody = try JSONEncoder().encode(body) }
        let (data, response) = try await session.data(for: request)
        guard let response = response as? HTTPURLResponse else { throw APIError.invalidResponse }
        if response.statusCode == 401 { throw APIError.unauthorized }
        guard (200...299).contains(response.statusCode) else {
            let error = try? JSONDecoder().decode([String: JSONValue].self, from: data)
            throw APIError.server(response.statusCode, error?["error"]?.description ?? error?["detail"]?.description ?? "The server could not complete this request")
        }
        if let envelope = try? JSONDecoder().decode([String: JSONValue].self, from: data), case .bool(false)? = envelope["ok"] {
            throw APIError.server(response.statusCode, envelope["error"]?.description ?? "The operation failed")
        }
        do { return try JSONDecoder().decode(type, from: data.isEmpty ? Data("{}".utf8) : data) }
        catch { throw APIError.invalidResponse }
    }
}
