import SwiftUI
import WolfBoxCore

struct TAView: View {
    @Bindable var model: AppModel
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 28) {
                PageHeading(title: "Start with the story.", subtitle: "Know what they’ve tried before office hours begin.")
                HStack(alignment: .top, spacing: 30) {
                    VStack(alignment: .leading, spacing: 14) {
                        SectionHeading(title: "Students", detail: "\(model.students.count)")
                        ForEach(model.students) { student in
                            Button { Task { await model.selectStudent(student.id) } } label: {
                                VStack(alignment: .leading, spacing: 10) {
                                    Text(student.name ?? student.id).font(.headline)
                                    if model.studentStates[student.id]?.nudge?.active == true {
                                        StatusLabel(text: "Could use a hand", symbol: "exclamationmark.circle.fill", color: .wolfRed)
                                    } else if model.studentStates[student.id] == nil && !model.fixtures { StatusLabel(text: "Box unavailable", symbol: "network.slash") }
                                    else { Text("No active nudge").font(.callout).foregroundStyle(.secondary) }
                                }.padding(18).frame(maxWidth: .infinity, alignment: .leading)
                                    .background(model.selectedStudent == student.id ? Color.wolfGreen.opacity(0.12) : Color.wolfSurface, in: RoundedRectangle(cornerRadius: 8))
                            }.buttonStyle(.plain).disabled(model.busy.contains("handoff"))
                        }
                        if model.students.isEmpty { Text("No students available. Refresh to try again.").foregroundStyle(.secondary) }
                    }.frame(width: 225)
                    VStack(alignment: .leading, spacing: 24) {
                        let student = model.students.first { $0.id == model.selectedStudent }
                        HStack {
                            Text(student?.name ?? "Select a student").font(.title2.weight(.semibold)); Spacer()
                            if let backend = student?.backend { Text("\(backend.capitalized) box").foregroundStyle(.secondary).font(.callout) }
                        }
                        if model.busy.contains("handoff") { ProgressView("Preparing the handoff…").controlSize(.small) }
                        if !model.summary.isEmpty { MarkdownText(text: model.summary).padding(24).background(Color.wolfSurface, in: RoundedRectangle(cornerRadius: 8)) }
                        SectionHeading(title: "Recent attempts", detail: "\(model.runs.count) runs")
                        if model.runs.isEmpty { Text("No attempts on record.").foregroundStyle(.secondary) }
                        ForEach(model.runs) { run in
                            DisclosureGroup {
                                TestResults(run: run).padding(.top, 12)
                                if let hint = run.hint { Text(hint).lineSpacing(4).padding(.vertical, 12) }
                            } label: {
                                HStack {
                                    Text((run.assignment ?? "Assignment").uppercased()).fontWeight(.semibold)
                                    Text(friendlyDate(run.ts)).foregroundStyle(.secondary)
                                    Spacer()
                                    Text("\((run.failed ?? []).count) failing").foregroundStyle((run.failed ?? []).isEmpty ? Color.wolfGreen : .wolfRed)
                                }
                            }.padding(14).background(Color.wolfSurface, in: RoundedRectangle(cornerRadius: 6))
                        }
                    }.frame(maxWidth: .infinity, alignment: .leading)
                }
            }.padding(30)
        }
    }
}
struct InstructorView: View {
    @Bindable var model: AppModel
    @State private var reset = false
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 28) {
                PageHeading(title: "See where the class gets stuck.", subtitle: "CSC 116 · Publish the next step, then see what needs another explanation.")
                VStack(spacing: 0) {
                    actionRow("HW5: Dictionaries & counting", detail: "Publish the assignment, starter code, and tests.", button: "Publish hw5") { await model.publish("hw5") }
                    Divider().padding(.horizontal, 20)
                    actionRow("HW4: List utilities · version 2", detail: "Clarify that safe_max([]) returns None.", button: "Update hw4 spec") { await model.publish("hw4-v2") }
                }.background(Color.wolfSurface, in: RoundedRectangle(cornerRadius: 8))
                HStack(alignment: .top, spacing: 32) {
                    VStack(alignment: .leading, spacing: 18) {
                        SectionHeading(title: "Mistake patterns", detail: model.heatmap?.students.map { "\($0) students" })
                        Text("Occurrences across all student boxes.").foregroundStyle(.secondary)
                        counts(model.heatmap?.mistake_tags ?? [:], color: .wolfGreen)
                    }.frame(maxWidth: .infinity)
                    VStack(alignment: .leading, spacing: 18) {
                        SectionHeading(title: "Tests to revisit")
                        Text("Failures that may deserve a class walkthrough.").foregroundStyle(.secondary)
                        counts(model.heatmap?.failing_tests ?? [:], color: .wolfRed)
                    }.frame(maxWidth: .infinity)
                }.padding(.vertical, 8)
                VStack(alignment: .leading, spacing: 12) {
                    SectionHeading(title: "Demo reset")
                    HStack { Text("Restore the initial course manifest for another rehearsal.").foregroundStyle(.secondary); Spacer(); Button("Reset course…", role: .destructive) { reset = true }.disabled(model.busy.contains("publish")) }
                }.padding(20).background(Color.wolfSurface, in: RoundedRectangle(cornerRadius: 8))
                if let message = model.notice { Text(message).font(.callout).foregroundStyle(.secondary) }
            }.padding(30)
        }
        .confirmationDialog("Restore the initial course manifest?", isPresented: $reset, titleVisibility: .visible) {
            Button("Reset course", role: .destructive) { Task { await model.resetCourse() } }
        } message: { Text("This resets the published demo course to its original set of documents.") }
    }
    func actionRow(_ title: String, detail: String, button: String, action: @escaping () async -> Void) -> some View {
        HStack(spacing: 24) { VStack(alignment: .leading, spacing: 7) { Text(title).font(.headline); Text(detail).foregroundStyle(.secondary) }; Spacer(); Button(button) { Task { await action() } }.controlSize(.large).disabled(model.busy.contains("publish")) }.padding(22)
    }
    func counts(_ values: [String: Int], color: Color) -> some View {
        VStack(alignment: .leading, spacing: 20) {
            if values.isEmpty { Text("No data recorded yet.").foregroundStyle(.secondary) }
            ForEach(values.keys.sorted(by: { values[$0, default: 0] > values[$1, default: 0] }), id: \.self) { key in
                VStack(spacing: 8) {
                    HStack { Text(key.replacingOccurrences(of: "_", with: " ").capitalized); Spacer(); Text("\(values[key, default: 0])").fontWeight(.semibold) }
                    GeometryReader { geometry in
                        Capsule().fill(color.opacity(0.08)).overlay(alignment: .leading) {
                            Capsule().fill(color.opacity(0.78)).frame(width: geometry.size.width * CGFloat(values[key, default: 0]) / CGFloat(max(1, values.values.max() ?? 1)))
                        }
                    }.frame(height: 12).accessibilityHidden(true)
                }.accessibilityElement(children: .combine)
            }
        }
    }
}
