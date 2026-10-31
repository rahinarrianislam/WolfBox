import SwiftUI
import WolfBoxCore

struct CanvasView: View {
    @Bindable var model: AppModel
    @State private var publishConfirmation = false
    var authorization: CanvasAuthorization { CanvasAuthorization(authorized: model.canvasAuthorized, role: model.user?.role ?? "") }
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 26) {
                PageHeading(title: "A course task, with you in control.", subtitle: "Delegate a Canvas action and follow every step.")
                VStack(alignment: .leading, spacing: 18) {
                    CanvasCoursePicker(model: model)
                    if model.user?.role == "instructor" {
                        LabeledContent("Staged item ID") { TextField("Staged assignment ID", text: $model.canvasAssignment).textFieldStyle(.roundedBorder).controlSize(.large) }
                    }
                    Toggle("I authorize WolfBox to perform the selected action in this Canvas course.", isOn: $model.canvasAuthorized)
                    Text("Instructor access is required. Publishing uses an existing staged item, such as hw5. Canvas uses the access token configured on the server.").foregroundStyle(.secondary).font(.callout)
                    HStack(spacing: 12) {
                        Button("Open course") { Task { await model.startCanvas("open_course") } }.disabled(!authorization.allows("open_course"))
                        Button("List assignments") { Task { await model.startCanvas("list_assignments") } }.disabled(!authorization.allows("list_assignments"))
                        if model.user?.role == "instructor" { Button("Publish assignment…") { publishConfirmation = true }.disabled(!authorization.allows("publish_assignment") || model.canvasAssignment.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty) }
                    }.controlSize(.large).disabled(model.busy.contains("canvas") || model.canvasCourse.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                }.padding(24).background(Color.wolfSurface, in: RoundedRectangle(cornerRadius: 8))
                if let task = model.delegateTask {
                    VStack(alignment: .leading, spacing: 22) {
                        HStack {
                            SectionHeading(title: "Task progress", detail: task.status?.replacingOccurrences(of: "_", with: " ").capitalized ?? "Unknown")
                            Button("Refresh status") { Task { await model.refreshCanvas() } }.disabled(model.busy.contains("canvas") || model.fixtures)
                        }
                        if task.mode == "fake" { StatusLabel(text: "Simulated task · no Canvas action", symbol: "square.stack.3d.up", color: .orange) }
                        if ["failed", "error", "denied"].contains(task.status ?? "") { StatusLabel(text: task.error ?? "The task could not be completed. Review its result below.", symbol: "exclamationmark.circle", color: .wolfRed) }
                        if model.busy.contains("canvas") { ProgressView("Following the task…").controlSize(.small) }
                        if model.delegateTimedOut { StatusLabel(text: "Status check timed out. Refresh to continue following this task.", symbol: "clock.badge.exclamationmark", color: .orange) }
                        ForEach(Array((task.steps ?? []).enumerated()), id: \.offset) { index, step in
                            HStack(alignment: .top, spacing: 16) {
                                Text("\(index + 1)").font(.body.weight(.semibold)).foregroundStyle(.secondary).frame(width: 20)
                                CanvasStep(step: step)
                            }
                        }
                        if let result = task.result, !result.description.isEmpty {
                            Text("Result").font(.headline)
                            CanvasResult(result: result)
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
                        Button("Refresh task history") { Task { await model.loadCanvasTasks() } }.disabled(model.fixtures || model.busy.contains("canvas-history"))
                        ForEach(Array(model.delegateTasks.enumerated()), id: \.offset) { _, task in
                            Button { Task { await model.openCanvasTask(task) } } label: {
                                HStack { Text(task.task_id ?? "Task"); Spacer(); if task.mode == "fake" { Text("Simulated").foregroundStyle(.orange) }; Text(task.status?.capitalized ?? "Unknown").foregroundStyle(.secondary) }
                            }.buttonStyle(.plain).disabled(model.busy.contains("canvas"))
                        }
                    }.padding(.top, 12)
                }
            }.padding(30)
        }
        .confirmationDialog("Publish this assignment to Canvas?", isPresented: $publishConfirmation, titleVisibility: .visible) {
            Button("Publish assignment") { Task { await model.startCanvas("publish_assignment") } }
        } message: { Text("\(model.canvasAssignment)\nCourse: \(model.canvasCourse)") }
        .onChange(of: model.canvasCourse) { _, _ in model.canvasAuthorized = false }
        .onChange(of: model.canvasAssignment) { _, _ in model.canvasAuthorized = false }
    }
}

private struct CanvasStep: View {
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
private struct CanvasResult: View {
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
