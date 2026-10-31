import SwiftUI
import AppKit
import WolfBoxCore

@main
struct WolfBoxApp: App {
    @State private var model = AppModel()
    init() { NSApplication.shared.setActivationPolicy(.regular) }
    var body: some Scene {
        WindowGroup("WolfBox") {
            RootView(model: model)
                .task {
                    if let index = ProcessInfo.processInfo.arguments.firstIndex(of: "--capture-screenshots"), ProcessInfo.processInfo.arguments.indices.contains(index + 1) {
                        await ScreenshotCapture.run(model: model, directory: ProcessInfo.processInfo.arguments[index + 1])
                    }
                }
        }.defaultSize(width: 1320, height: 920)
        .commands { CommandGroup(replacing: .newItem) {} }
    }
}

#Preview("Student workspace") { RootView(model: AppModel(fixtures: true)).frame(width: 1320, height: 920) }
#Preview("Course") {
    let model = AppModel(fixtures: true)
    model.destination = .course
    return RootView(model: model).frame(width: 1320, height: 920)
}
#Preview("Planner") {
    let model = AppModel(fixtures: true)
    model.destination = .plan
    return RootView(model: model).frame(width: 1320, height: 920)
}
#Preview("TA") {
    let model = AppModel(fixtures: true)
    model.loadFixtures(role: "ta")
    return RootView(model: model).frame(width: 1320, height: 920)
}
#Preview("Instructor") {
    let model = AppModel(fixtures: true)
    model.loadFixtures(role: "instructor")
    return RootView(model: model).frame(width: 1320, height: 920)
}
