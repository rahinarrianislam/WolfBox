import SwiftUI
import WolfBoxCore

struct LearnView: View {
    @Bindable var model: AppModel
    @State private var showingDraft = false
    @State private var draft = ""
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 26) {
                HStack(alignment: .top) {
                    PageHeading(title: model.assignments.first(where: { $0.id == model.assignment })?.title ?? "Your coding workspace", subtitle: "CSC 116 · Every attempt adds to your story.")
                    Picker("Assignment", selection: Binding(get: { model.assignment }, set: { target in Task { await model.selectAssignment(target) } })) {
                        if model.assignments.isEmpty { Text(model.assignment.uppercased()).tag(model.assignment) }
                        ForEach(model.assignments) { Text($0.id.uppercased()).tag($0.id) }
                    }.frame(width: 145).disabled(model.isRunning || model.busy.contains("student"))
                }
                HStack(alignment: .top, spacing: 26) {
                    VStack(alignment: .leading, spacing: 24) {
                        VStack(spacing: 0) {
                            HStack {
                                Text("\(model.assignment).py").font(.body.weight(.semibold))
                                Spacer()
                                Text("Python").foregroundStyle(.secondary).font(.callout)
                            }.padding(.horizontal, 18).padding(.vertical, 14).background(Color.wolfSurface)
                            CodeEditor(text: Binding(get: { model.code }, set: model.editCode)).frame(height: 304)
                            HStack {
                                if model.isRunning { ProgressView().controlSize(.small); Text("Running in your box…").font(.callout) }
                                else { Text("Tab inserts 4 spaces").font(.caption).foregroundStyle(.secondary) }
                                Spacer()
                                Button { Task { await model.runTests() } } label: { Label("Run tests", systemImage: "play.fill") }
                                    .buttonStyle(.borderedProminent).controlSize(.large).keyboardShortcut(.return, modifiers: .command)
                                    .disabled(model.isRunning || model.busy.contains("student") || model.code.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                            }.padding(14).background(Color.wolfSurface)
                        }.clipShape(RoundedRectangle(cornerRadius: 8))
                        VStack(alignment: .leading, spacing: 12) {
                            SectionHeading(title: "Ask your tutor")
                            Text("A question about your code, with your past attempts in mind.").foregroundStyle(.secondary)
                            HStack {
                                TextField("Why does the last-index test fail?", text: $model.question).textFieldStyle(.roundedBorder).onSubmit { Task { await model.askTutor() } }
                                Button("Ask") { Task { await model.askTutor() } }.disabled(model.busy.contains("ask") || model.question.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                            }.controlSize(.large)
                            if model.busy.contains("ask") { ProgressView("Thinking…").controlSize(.small) }
                            if !model.answer.isEmpty { MarkdownText(text: model.answer).padding(.top, 4) }
                        }
                        if let due = model.assignments.first(where: { $0.id == model.assignment })?.due {
                            Label("Due \(friendlyDate(due))", systemImage: "calendar").font(.callout).foregroundStyle(.secondary)
                        }
                    }.frame(maxWidth: .infinity)
                    VStack(alignment: .leading, spacing: 24) {
                        TestResults(run: model.run, running: model.isRunning, timeout: model.runTimedOut)
                        if let run = model.run, run.hint_status == "pending" || run.hint != nil {
                            VStack(alignment: .leading, spacing: 13) {
                                SectionHeading(title: "A hint, with history")
                                if run.hint_status == "pending" { ProgressView("Thinking about your past attempts…").controlSize(.small) }
                                else { Text(run.hint ?? "No hint was returned.").font(.system(size: 15)).lineSpacing(5).textSelection(.enabled) }
                                ForEach(Array((run.related_past ?? []).enumerated()), id: \.offset) { _, related in
                                    Text("\(related.assignment ?? "Past run") · \(related.tag ?? "pattern")").font(.callout.weight(.medium)).padding(.horizontal, 9).padding(.vertical, 5).background(Color.wolfGold.opacity(0.22), in: RoundedRectangle(cornerRadius: 5))
                                }
                                if let modelName = run.llm?.model { Text("via \(modelName)").font(.caption).foregroundStyle(.secondary) }
                            }.padding(20).frame(maxWidth: .infinity, alignment: .leading).background(Color.wolfGreen.opacity(0.08), in: RoundedRectangle(cornerRadius: 8))
                        }
                        VStack(alignment: .leading, spacing: 12) {
                            SectionHeading(title: "Patterns remembered")
                            let counts = model.state?.profile?.mistake_counts ?? [:]
                            if counts.isEmpty { Text("Your history starts with your first run.").foregroundStyle(.secondary) }
                            ForEach(counts.keys.sorted(by: { counts[$0, default: 0] > counts[$1, default: 0] }), id: \.self) { tag in
                                HStack { Text(tag.replacingOccurrences(of: "_", with: " ").capitalized); Spacer(); Text("\(counts[tag, default: 0])").fontWeight(.semibold).foregroundStyle(.secondary) }
                            }
                        }
                    }.frame(width: 335)
                }
                if model.state?.nudge?.active == true {
                    HStack(alignment: .top, spacing: 16) {
                        Image(systemName: "person.fill.questionmark").font(.title2).foregroundStyle(Color.wolfGreen)
                        VStack(alignment: .leading, spacing: 7) {
                            Text("A good time for office hours.").font(.headline)
                            Text(model.state?.nudge?.reason ?? "You’ve been working through the same failure.").foregroundStyle(.secondary)
                            Text(model.state?.nudge?.draft ?? "A message to your TA is ready to draft.").lineSpacing(3)
                        }
                        Spacer(minLength: 16)
                        Button("Review message…") { draft = model.state?.nudge?.draft ?? ""; showingDraft = true }
                    }.padding(20).background(Color.wolfGold.opacity(0.16), in: RoundedRectangle(cornerRadius: 8))
                }
            }.padding(30)
        }
        .sheet(isPresented: $showingDraft) {
            VStack(alignment: .leading, spacing: 18) {
                Text("Ask your TA for a hand").font(.title2.weight(.semibold))
                Text("Review the draft, then choose a recipient in Mail. WolfBox doesn’t have an office-hours queue endpoint.").foregroundStyle(.secondary)
                TextEditor(text: $draft).font(.body).frame(height: 160).accessibilityLabel("Message to TA")
                HStack {
                    Button("Cancel") { showingDraft = false }; Spacer()
                    ShareLink(item: draft) { Label("Send…", systemImage: "paperplane") }.buttonStyle(.borderedProminent)
                }
            }.padding(28).frame(width: 520)
        }
    }
}
struct TestResults: View {
    var run: Run?; var running = false; var timeout = false
    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            SectionHeading(title: "Test results", detail: run.map { "\(($0.passed ?? []).count) of \(($0.passed ?? []).count + ($0.failed ?? []).count) passed" })
            if timeout { StatusLabel(text: "Timed out · refresh to check", symbol: "clock.badge.exclamationmark", color: .orange) }
            if let run {
                ForEach(run.passed ?? [], id: \.self) { name in test(name, symbol: "checkmark.circle.fill", color: .wolfGreen) }
                ForEach(Array((run.failed ?? []).enumerated()), id: \.offset) { _, failure in
                    VStack(alignment: .leading, spacing: 8) {
                        test(failure.test ?? "Test failed", symbol: "xmark.circle.fill", color: .wolfRed)
                        if let message = failure.message { Text(String(message.prefix(400))).font(.callout).lineSpacing(3).foregroundStyle(Color.wolfRed).textSelection(.enabled).padding(.leading, 25) }
                    }
                }
                if run.status == "error" { StatusLabel(text: "The test runner reported an error.", symbol: "exclamationmark.circle", color: .wolfRed) }
                if run.hint_status == "failed" { Text("The hint could not be generated. You can still ask the tutor.").font(.callout).foregroundStyle(.secondary) }
            } else if running { ProgressView("Running your assignment tests…").controlSize(.small) }
            else { Text("Run your code to see each test here.").foregroundStyle(.secondary).padding(.vertical, 16) }
        }
    }
    func test(_ name: String, symbol: String, color: Color) -> some View {
        Label(name, systemImage: symbol).font(.body).foregroundStyle(color).accessibilityLabel("\(name), \(symbol.hasPrefix("checkmark") ? "passed" : "failed")")
    }
}
