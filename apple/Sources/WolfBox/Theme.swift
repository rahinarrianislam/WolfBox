import SwiftUI

extension Color {
    static let wolfBrand = Color(red: 0.17, green: 0.31, blue: 0.26)
    static let wolfGreen = Color(nsColor: NSColor(name: nil) { $0.bestMatch(from: [.darkAqua, .aqua]) == .darkAqua ? NSColor(calibratedRed: 0.62, green: 0.80, blue: 0.70, alpha: 1) : NSColor(calibratedRed: 0.17, green: 0.31, blue: 0.26, alpha: 1) })
    static let wolfCalendarBlue = Color(nsColor: NSColor(name: nil) { $0.bestMatch(from: [.darkAqua, .aqua]) == .darkAqua ? NSColor(calibratedRed: 0.20, green: 0.31, blue: 0.43, alpha: 1) : NSColor(calibratedRed: 0.8, green: 0.86, blue: 0.94, alpha: 1) })
    static let wolfCalendarPink = Color(nsColor: NSColor(name: nil) { $0.bestMatch(from: [.darkAqua, .aqua]) == .darkAqua ? NSColor(calibratedRed: 0.42, green: 0.25, blue: 0.23, alpha: 1) : NSColor(calibratedRed: 0.95, green: 0.82, blue: 0.78, alpha: 1) })
    static let wolfPaper = Color(nsColor: NSColor(name: nil) { $0.bestMatch(from: [.darkAqua, .aqua]) == .darkAqua ? NSColor(calibratedRed: 0.10, green: 0.13, blue: 0.12, alpha: 1) : NSColor(calibratedRed: 0.96, green: 0.96, blue: 0.93, alpha: 1) })
    static let wolfSurface = Color(nsColor: .controlBackgroundColor)
    static let wolfGold = Color(red: 0.96, green: 0.73, blue: 0.17)
    static let wolfRed = Color(nsColor: NSColor(name: nil) { $0.bestMatch(from: [.darkAqua, .aqua]) == .darkAqua ? NSColor(calibratedRed: 1, green: 0.57, blue: 0.50, alpha: 1) : NSColor(calibratedRed: 0.72, green: 0.18, blue: 0.14, alpha: 1) })
}
struct PageHeading: View {
    var title: String; var subtitle: String
    var body: some View {
        VStack(alignment: .leading, spacing: 7) {
            Text(title).font(.system(size: 30, weight: .semibold)).tracking(-0.8)
            Text(subtitle).font(.body).foregroundStyle(.secondary)
        }.frame(maxWidth: .infinity, alignment: .leading)
    }
}
struct SectionHeading: View {
    var title: String; var detail: String? = nil
    var body: some View {
        HStack(alignment: .firstTextBaseline) {
            Text(title).font(.title3.weight(.semibold))
            Spacer()
            if let detail { Text(detail).font(.callout).foregroundStyle(.secondary) }
        }
    }
}
struct StatusLabel: View {
    var text: String; var symbol: String; var color: Color = .secondary
    var body: some View {
        Label(text, systemImage: symbol).font(.callout.weight(.medium)).foregroundStyle(color)
    }
}
struct MarkdownText: View {
    var text: String
    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            ForEach(Array(text.components(separatedBy: "\n\n").enumerated()), id: \.offset) { _, paragraph in
                if paragraph.hasPrefix("#") {
                    Text(paragraph.trimmingCharacters(in: CharacterSet(charactersIn: "# "))).font(.title3.weight(.semibold)).padding(.top, 6)
                } else {
                    Text((try? AttributedString(markdown: paragraph, options: .init(interpretedSyntax: .inlineOnlyPreservingWhitespace))) ?? AttributedString(paragraph))
                        .font(.body).lineSpacing(5).fixedSize(horizontal: false, vertical: true)
                }
            }
        }.textSelection(.enabled).frame(maxWidth: .infinity, alignment: .leading)
    }
}
func friendlyDate(_ value: String?) -> String {
    guard let value else { return "No due date" }
    let iso = ISO8601DateFormatter()
    guard let date = iso.date(from: value) else { return value }
    return date.formatted(.dateTime.month(.abbreviated).day().hour().minute())
}
func safeWebURL(_ value: String?) -> URL? {
    guard let value, let url = URL(string: value), ["http", "https"].contains(url.scheme?.lowercased() ?? ""), url.host != nil, url.user == nil, url.password == nil else { return nil }
    return url
}
