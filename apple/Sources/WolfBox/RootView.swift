import SwiftUI
import WolfBoxCore

struct RootView: View {
    @Bindable var model: AppModel
    @State private var settings = false
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    var body: some View {
        Group {
            if model.user == nil { AuthView(model: model, settings: $settings) }
            else { workspace }
        }
        .tint(.wolfGreen)
        .frame(minWidth: 1080, minHeight: 740)
        .sheet(isPresented: $settings) { ServerSettings(model: model) }
        .task { await model.restoreSession() }
    }
    var workspace: some View {
        NavigationSplitView {
            VStack(alignment: .leading, spacing: 0) {
                VStack(alignment: .leading, spacing: 5) {
                    Text("WolfBox").font(.system(size: 25, weight: .bold)).tracking(-0.8)
                    Text("Your work, remembered.").font(.callout).foregroundStyle(.secondary)
                }.padding(.horizontal, 20).padding(.top, 25).padding(.bottom, 24)
                List(selection: Binding<Destination?>(get: { model.destination }, set: { if let value = $0 { model.destination = value } })) {
                    ForEach(model.destinations) { item in
                        HStack(spacing: 9) {
                            Image(systemName: item.symbol).foregroundStyle(Color.wolfGreen).frame(width: 20)
                            Text(item.rawValue)
                        }.accessibilityElement(children: .combine).tag(item).padding(.vertical, 6)
                    }
                }.listStyle(.sidebar)
                VStack(alignment: .leading, spacing: 8) {
                    if model.fixtures {
                        Label("Demo fixtures", systemImage: "square.stack.3d.up").font(.callout.weight(.semibold))
                        Text("Sample records. No server calls.").font(.caption).foregroundStyle(.secondary)
                    } else {
                        Label("Local demo account", systemImage: "person.crop.circle").font(.callout)
                        Text(model.serverURL).font(.caption).foregroundStyle(.secondary).lineLimit(2)
                    }
                    Divider().padding(.vertical, 7)
                    Text(model.user?.name ?? "Your workspace").font(.body.weight(.semibold))
                    Text(model.user?.role == "ta" ? "TA" : (model.user?.role ?? "student").capitalized).font(.caption).foregroundStyle(.secondary)
                }.padding(20)
            }.navigationSplitViewColumnWidth(min: 210, ideal: 225, max: 260)
        } detail: {
            VStack(spacing: 0) {
                if let error = model.error { message(error, error: true) }
                if let notice = model.notice { message(notice, error: false) }
                Group {
                    switch model.destination {
                    case .learn: LearnView(model: model)
                    case .course: CourseView(model: model)
                    case .plan: PlanView(model: model)
                    case .ta: TAView(model: model)
                    case .instructor: InstructorView(model: model)
                    case .canvas: CanvasView(model: model)
                    }
                }.frame(maxWidth: .infinity, maxHeight: .infinity)
            }
            .background(Color.wolfPaper)
            .navigationTitle(model.destination.rawValue)
            .toolbar {
                ToolbarItem(placement: .automatic) {
                    if model.user?.role == "student" { StatusLabel(text: model.state?.llm?.caption ?? "Gemma 4 · unavailable", symbol: model.state?.llm?.active_backend == "ollama" ? "network.slash" : "cpu").labelStyle(.titleAndIcon).fixedSize() }
                }
                ToolbarItem(placement: .automatic) {
                    Button { Task { await model.loadDestination() } } label: { Label("Refresh", systemImage: "arrow.clockwise") }
                        .disabled(!model.busy.isEmpty || model.fixtures).help("Refresh this view")
                }
                ToolbarItem(placement: .automatic) {
                    Menu {
                        Button("Server settings…") { settings = true }
                        if model.fixtures {
                            Divider()
                            ForEach(["student", "ta", "instructor"], id: \.self) { role in Button("Preview \(role == "ta" ? "TA" : role.capitalized)") { model.loadFixtures(role: role) } }
                        }
                        Divider()
                        Button("Sign out") { Task { await model.logout() } }
                    } label: { Label("Account", systemImage: "person.crop.circle") }
                }
            }
            .task(id: "\(model.user?.id ?? "")-\(model.destination.rawValue)") { await model.loadDestination() }
        }
        .animation(reduceMotion ? nil : .spring(response: 0.3, dampingFraction: 1), value: model.destination)
    }
    func message(_ text: String, error: Bool) -> some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: error ? "exclamationmark.circle" : "info.circle")
            Text(text).textSelection(.enabled).frame(maxWidth: .infinity, alignment: .leading)
            Button { if error { model.error = nil } else { model.notice = nil } } label: { Image(systemName: "xmark") }.buttonStyle(.plain).accessibilityLabel("Dismiss message")
        }.font(.callout).padding(14).background(error ? Color.wolfRed.opacity(0.1) : Color.wolfGreen.opacity(0.08))
    }
}

struct ServerSettings: View {
    @Bindable var model: AppModel
    @State private var value = ""
    @State private var error: String?
    @Environment(\.dismiss) private var dismiss
    var body: some View {
        VStack(alignment: .leading, spacing: 20) {
            Text("Server settings").font(.title2.weight(.semibold))
            Text("Connect to the orchestrator on this laptop or your demo server. Changing servers signs you out.").foregroundStyle(.secondary)
            TextField("Server URL", text: $value).textFieldStyle(.roundedBorder)
            if let error { Text(error).foregroundStyle(Color.wolfRed) }
            HStack { Spacer(); Button("Cancel") { dismiss() }; Button("Save") { do { try model.changeServer(value); dismiss() } catch { self.error = error.localizedDescription } }.keyboardShortcut(.defaultAction).buttonStyle(.borderedProminent) }
        }.padding(28).frame(width: 480).onAppear { value = model.serverURL }
    }
}

struct AuthView: View {
    @Bindable var model: AppModel
    @Binding var settings: Bool
    var initialSignup = false
    @State private var signup = false
    @State private var name = ""
    @State private var email = ""
    @State private var password = ""
    @State private var role = "student"
    var body: some View {
        HStack(spacing: 0) {
            VStack(alignment: .leading, spacing: 0) {
                Text("WolfBox").font(.system(size: 34, weight: .bold)).tracking(-1)
                Spacer()
                Text("AI tutors\nforget you.").font(.system(size: 47, weight: .medium)).tracking(-1.6)
                Text("WolfBox\nremembers.").font(.system(size: 47, weight: .semibold)).tracking(-1.6).foregroundStyle(Color.wolfGold).padding(.top, 16)
                Text("And so does your TA.").font(.title3).padding(.top, 22)
                Spacer()
                Text("One persistent workspace.\nEvery attempt carries forward.").font(.body).lineSpacing(6).foregroundStyle(.white.opacity(0.8))
            }.padding(48).frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .leading).background(Color.wolfBrand).foregroundStyle(.white)
            VStack(alignment: .leading, spacing: 22) {
                PageHeading(title: signup ? "Make yourself at home." : "Pick up where you left off.", subtitle: "Use an email and password for this local demo.")
                Picker("Account", selection: $signup) { Text("Sign in").tag(false); Text("Create account").tag(true) }.pickerStyle(.segmented)
                VStack(alignment: .leading, spacing: 14) {
                    if signup { field("Name") { TextField("Your name", text: $name) } }
                    field("Email") { TextField("you@example.com", text: $email).textContentType(.username) }
                    field("Password") { SecureField("Password", text: $password).textContentType(signup ? .newPassword : .password) }
                    if signup { Picker("Role", selection: $role) { Text("Student").tag("student"); Text("TA").tag("ta"); Text("Instructor").tag("instructor") } }
                }.textFieldStyle(.roundedBorder).controlSize(.large)
                if let error = model.error { Text(error).foregroundStyle(Color.wolfRed).font(.callout).textSelection(.enabled) }
                if model.busy.contains("auth") {
                    HStack(spacing: 12) { ProgressView().controlSize(.small); Text(signup && role == "student" ? "Creating your account and provisioning your box. This can take a few seconds…" : "Connecting to your local account…").font(.callout) }
                }
                Button(signup ? "Create account" : "Sign in") {
                    Task { await model.authenticate(email: email, password: password, name: name, role: role, signup: signup); password = "" }
                }.buttonStyle(.borderedProminent).controlSize(.large).keyboardShortcut(.defaultAction)
                    .disabled(model.busy.contains("auth") || email.trimmingCharacters(in: .whitespaces).isEmpty || password.isEmpty || (signup && name.trimmingCharacters(in: .whitespaces).isEmpty))
                HStack { Text(model.serverURL).font(.caption).foregroundStyle(.secondary); Button("Change…") { settings = true }.buttonStyle(.link) }
                Spacer().frame(height: 5)
                Button("Explore a sample workspace") { model.fixtures = true; model.error = nil; model.loadFixtures() }.buttonStyle(.link).font(.callout)
            }.padding(52).frame(maxWidth: .infinity).disabled(model.busy.contains("auth"))
        }.background(Color.wolfPaper).onAppear { signup = initialSignup }
    }
    func field<Content: View>(_ title: String, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 6) { Text(title).font(.callout.weight(.medium)); content().accessibilityLabel(title) }
    }
}
