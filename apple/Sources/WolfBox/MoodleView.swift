import SwiftUI
import WolfBoxCore

struct MoodleView: View {
    @Bindable var model: AppModel
    @State private var publishConfirmation = false
    var authorization: MoodleAuthorization { MoodleAuthorization(authorized: model.moodleAuthorized, role: model.user?.role ?? "") }
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 26) {
                PageHeading(title: "A course task, with you in control.", subtitle: "Delegate a Moodle action and follow every step.")
                VStack(alignment: .leading, spacing: 18) {
                    LabeledContent("Course ID") { TextField("Course ID", text: $model.moodleCourse).textFieldStyle(.roundedBorder).controlSize(.large) }
                    if model.user?.role == "instructor" {
                        LabeledContent("Staged item ID") { TextField("Staged assignment ID", text: $model.moodleAssignment).textFieldStyle(.roundedBorder).controlSize(.large) }
                    }
                    Toggle("I authorize WolfBox to perform the selected action in this Moodle course.", isOn: $model.moodleAuthorized)
                    Text("Instructor access is required. Publishing uses an existing staged item, such as hw5. If Moodle needs your sign-in, use the task’s takeover link.").foregroundStyle(.secondary).font(.callout)
                    HStack(spacing: 12) {
                        Button("Open course") { Task { await model.startMoodle("open_course") } }.disabled(!authorization.allows("open_course"))
                        Button("List assignments") { Task { await model.startMoodle("list_assignments") } }.disabled(!authorization.allows("list_assignments"))
                        if model.user?.role == "instructor" { Button("Publish assignment…") { publishConfirmation = true }.disabled(!authorization.allows("publish_assignment") || model.moodleAssignment.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty) }
                    }.controlSize(.large).disabled(model.busy.contains("moodle") || model.moodleCourse.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                }.padding(24).background(Color.wolfSurface, in: RoundedRectangle(cornerRadius: 8))
                if let task = model.delegateTask {
                    VStack(alignment: .leading, spacing: 22) {
                        HStack {
                            SectionHeading(title: "Task progress", detail: task.status?.replacingOccurrences(of: "_", with: " ").capitalized ?? "Unknown")
                            Button("Refresh status") { Task { await model.refreshMoodle() } }.disabled(model.busy.contains("moodle") || model.fixtures)
                        }
                        if task.mode == "fake" { StatusLabel(text: "Simulated task · no Moodle action", symbol: "square.stack.3d.up", color: .orange) }
                        if ["failed", "error", "denied"].contains(task.status ?? "") { StatusLabel(text: task.error ?? "The task could not be completed. Review its result below.", symbol: "exclamationmark.circle", color: .wolfRed) }
                        if model.busy.contains("moodle") { ProgressView("Following the task…").controlSize(.small) }
                        if model.delegateTimedOut { StatusLabel(text: "Status check timed out. Refresh to continue following this task.", symbol: "clock.badge.exclamationmark", color: .orange) }
                        ForEach(Array((task.steps ?? []).enumerated()), id: \.offset) { index, step in
                            HStack(alignment: .top, spacing: 16) {
                                Text("\(index + 1)").font(.body.weight(.semibold)).foregroundStyle(.secondary).frame(width: 20)
                                MoodleStep(step: step)
                            }
                        }
                        if let result = task.result, !result.description.isEmpty {
                            Text("Result").font(.headline)
                            MoodleResult(result: result)
                        }
                        if let error = task.error { Text(error).foregroundStyle(Color.wolfRed).textSelection(.enabled) }
                        HStack(spacing: 20) {
                            if let url = safeWebURL(task.watch_url) { Link(destination: url) { Label("Watch task", systemImage: "play.rectangle") } }
                            if let url = safeWebURL(task.takeover_url) { Link(destination: url) { Label("Take over", systemImage: "hand.point.up.left") } }
                        }
                        Text(task.task_id ?? "Task ID unavailable").font(.caption).foregroundStyle(.secondary).textSelection(.enabled)
                    }.padding(24).background(Color.wolfGreen.opacity(0.06), in: RoundedRectangle(cornerRadius: 8))
                } else {
                    ContentUnavailableView("Ready when you are", systemImage: "arrow.up.forward.app", description: Text("Choose a course, authorize an action, and start a task. Nothing runs before you ask."))
                }
                DisclosureGroup("Task history (\(model.delegateTasks.count))") {
                    VStack(alignment: .leading, spacing: 12) {
                        Button("Refresh task history") { Task { await model.loadMoodleTasks() } }.disabled(model.fixtures || model.busy.contains("moodle-history"))
                        ForEach(Array(model.delegateTasks.enumerated()), id: \.offset) { _, task in
                            Button { Task { await model.openMoodleTask(task) } } label: {
                                HStack { Text(task.task_id ?? "Task"); Spacer(); if task.mode == "fake" { Text("Simulated").foregroundStyle(.orange) }; Text(task.status?.capitalized ?? "Unknown").foregroundStyle(.secondary) }
                            }.buttonStyle(.plain).disabled(model.busy.contains("moodle"))
                        }
                    }.padding(.top, 12)
                }
            }.padding(30)
        }
        .confirmationDialog("Publish this assignment to Moodle?", isPresented: $publishConfirmation, titleVisibility: .visible) {
            Button("Publish assignment") { Task { await model.startMoodle("publish_assignment") } }
        } message: { Text("\(model.moodleAssignment)\nCourse: \(model.moodleCourse)") }
        .onChange(of: model.moodleCourse) { _, _ in model.moodleAuthorized = false }
        .onChange(of: model.moodleAssignment) { _, _ in model.moodleAuthorized = false }
    }
}

private struct MoodleStep: View {
    var step: JSONValue
    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            if case .object(let fields) = step {
                Text((fields["description"] ?? fields["text"] ?? fields["action"] ?? fields["message"])?.description ?? "Task step").textSelection(.enabled)
                if let status = fields["status"] { Label(status.description.replacingOccurrences(of: "_", with: " ").capitalized, systemImage: status.description == "done" ? "checkmark.circle" : "circle.dotted").font(.callout).foregroundStyle(.secondary) }
            } else { Text(step.description).textSelection(.enabled) }
        }
    }
}
private struct MoodleResult: View {
    var result: JSONValue
    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            if case .object(let fields) = result {
                ForEach(fields.keys.sorted(), id: \.self) { key in
                    VStack(alignment: .leading, spacing: 6) {
                        Text(key.replacingOccurrences(of: "_", with: " ").capitalized).font(.callout.weight(.semibold)).foregroundStyle(.secondary)
                        Text(fields[key]?.description ?? "").lineSpacing(5).textSelection(.enabled)
                    }
                }
            } else { Text(result.description).lineSpacing(5).textSelection(.enabled) }
        }
    }
}
