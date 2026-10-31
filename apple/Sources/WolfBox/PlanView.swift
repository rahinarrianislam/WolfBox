import SwiftUI
import WolfBoxCore

struct PlanView: View {
    @Bindable var model: AppModel
    @State private var savedText: String?
    var options: [ScheduleOption] { model.plan?.options ?? model.plan?.plan?.last_options ?? [] }
    var selected: ScheduleOption? { options.indices.contains(model.optionIndex) ? options[model.optionIndex] : nil }
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                PageHeading(title: "Make room for your life.", subtitle: "Registration plans built from real sections and your preferences.")
                HStack(spacing: 8) {
                    Image(systemName: model.plan?.catalog?.sample == false ? "checkmark.seal" : "info.circle")
                    Text((model.plan?.catalog ?? model.plan?.plan?.catalog)?.caption ?? "Catalog unavailable").textSelection(.enabled)
                }.font(.callout).foregroundStyle(.secondary)
                VStack(alignment: .leading, spacing: 12) {
                    Text("What should your week look like?").font(.headline)
                    HStack {
                        TextField("No 8 AMs. I work Tuesday and Thursday afternoons…", text: $model.prefs).textFieldStyle(.roundedBorder)
                        Button(model.busy.contains("prefs") ? "Saving…" : "Save preferences") { Task { await model.savePrefs(); if model.error == nil { savedText = model.prefs } } }.disabled(model.busy.contains("prefs") || model.busy.contains("solve") || model.prefs.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                        Button("Find schedules") { Task { await model.solvePlan() } }.buttonStyle(.borderedProminent).disabled(model.busy.contains("solve") || model.busy.contains("prefs") || model.echo.isEmpty || (savedText != nil && savedText != model.prefs))
                    }.controlSize(.large)
                    if !model.echo.isEmpty { Label(model.echo, systemImage: "checkmark.circle").font(.callout).foregroundStyle(Color.wolfGreen).textSelection(.enabled) }
                    if savedText != nil && savedText != model.prefs { Text("Save the changed preferences before finding schedules.").font(.caption).foregroundStyle(.secondary) }
                }
                if model.busy.contains("solve") { ProgressView("Checking prerequisites, time conflicts, and preferences…").controlSize(.small) }
                if options.isEmpty {
                    ContentUnavailableView("A week that works for you", systemImage: "calendar", description: Text("Save your preferences, review the echo, then find schedules. If no options match, loosen one constraint and try again."))
                } else {
                    HStack(alignment: .top, spacing: 26) {
                        VStack(alignment: .leading, spacing: 16) {
                            Picker("Schedule option", selection: $model.optionIndex) {
                                ForEach(options.indices, id: \.self) { index in Text("Option \(index + 1) · \(options[index].credits ?? 0) credits").tag(index) }
                            }.pickerStyle(.segmented)
                            if let selected {
                                HStack { Text(selected.explanation ?? "").lineSpacing(3); Spacer(); if let rating = selected.avg_rating { Label(String(format: "%.1f avg", rating), systemImage: "star.fill").font(.callout.weight(.semibold)).foregroundStyle(Color.wolfGreen).fixedSize() } }
                                WeekCalendar(sections: selected.sections ?? [])
                                SectionHeading(title: "Your sections", detail: "\(selected.credits ?? 0) credits")
                                ForEach(Array((selected.sections ?? []).enumerated()), id: \.offset) { _, section in SectionRow(section: section) }
                            }
                        }.frame(maxWidth: .infinity)
                        VStack(alignment: .leading, spacing: 20) {
                            SectionHeading(title: "Still to go")
                            Text("Based on completed courses, before this plan.").font(.callout).foregroundStyle(.secondary)
                            ForEach(Array((model.plan?.remaining ?? []).enumerated()), id: \.offset) { _, requirement in
                                VStack(alignment: .leading, spacing: 7) {
                                    Text(requirement.name ?? requirement.id ?? "Requirement").font(.headline)
                                    Text("\(requirement.remaining ?? 0) of \(requirement.courses_needed ?? 0) courses remaining").font(.callout).foregroundStyle(.secondary)
                                    Text((requirement.options ?? []).joined(separator: " · ")).font(.caption).foregroundStyle(.secondary)
                                }
                            }
                        }.padding(20).frame(width: 210, alignment: .leading).background(Color.wolfSurface, in: RoundedRectangle(cornerRadius: 8))
                    }
                }
            }.padding(30)
        }.onAppear { if !model.echo.isEmpty { savedText = model.prefs } }
    }
}
struct WeekCalendar: View {
    var sections: [CourseSection]
    var layout: WeekLayout { WeekLayout(sections: sections) }
    var days: [String] {
        let standard = ["Mon", "Tue", "Wed", "Thu", "Fri"]
        let extra = Set(layout.meetings.map(\.day)).subtracting(standard)
        return standard + ["Sat", "Sun"].filter(extra.contains) + extra.subtracting(["Sat", "Sun"]).sorted()
    }
    let scale: CGFloat = 0.68
    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 0) { Text("").frame(width: 44); ForEach(days, id: \.self) { Text($0).font(.callout.weight(.medium)).frame(maxWidth: .infinity) } }.padding(.vertical, 11)
            HStack(alignment: .top, spacing: 0) {
                ZStack(alignment: .topTrailing) {
                    Color.clear
                    ForEach(Array(stride(from: layout.startMinute, through: layout.endMinute, by: 60)), id: \.self) { minute in
                        Text(String(format: "%02d:00", minute / 60)).font(.caption2).foregroundStyle(.secondary).offset(y: CGFloat(minute - layout.startMinute) * scale - 6)
                    }
                }.frame(width: 40).padding(.trailing, 4)
                ForEach(days, id: \.self) { day in
                    GeometryReader { geometry in
                        ZStack(alignment: .topLeading) {
                            Rectangle().fill(Color.primary.opacity(0.025))
                            ForEach(Array(stride(from: layout.startMinute, through: layout.endMinute, by: 60)), id: \.self) { minute in
                                Rectangle().fill(Color.primary.opacity(0.07)).frame(height: 1).offset(y: CGFloat(minute - layout.startMinute) * scale)
                            }
                            ForEach(layout.meetings.filter { $0.day == day }) { meeting in
                                VStack(alignment: .leading, spacing: 2) {
                                    Text(meeting.section.course ?? "Class").font(.caption.weight(.semibold))
                                    Text(meeting.section.start ?? "").font(.caption2)
                                }.padding(.horizontal, 6).padding(.vertical, 4)
                                    .frame(width: max(0, geometry.size.width - 6), height: max(24, CGFloat(meeting.end - meeting.start) * scale - 2), alignment: .topLeading)
                                    .background(color(for: meeting.section.course), in: RoundedRectangle(cornerRadius: 4))
                                    .offset(x: 3, y: CGFloat(meeting.start - layout.startMinute) * scale)
                                    .accessibilityElement(children: .ignore)
                                    .accessibilityLabel("\(meeting.section.course ?? "Class"), \(day), \(meeting.section.start ?? "") to \(meeting.section.end ?? "")")
                            }
                        }
                    }
                }
            }.frame(height: CGFloat(layout.endMinute - layout.startMinute) * scale + 10)
        }.padding(12).background(Color.wolfSurface, in: RoundedRectangle(cornerRadius: 8))
    }
    func color(for course: String?) -> Color {
        let index = sections.firstIndex { $0.course == course } ?? 0
        return [Color.wolfGreen.opacity(0.18), Color.wolfCalendarBlue, Color.wolfGold.opacity(0.30), Color.wolfCalendarPink][index % 4]
    }
}
struct SectionRow: View {
    var section: CourseSection
    var body: some View {
        HStack(alignment: .top, spacing: 16) {
            VStack(alignment: .leading, spacing: 5) { Text(section.course ?? "Course").font(.headline); Text(section.section_id ?? "Section unavailable").font(.caption).foregroundStyle(.secondary) }.frame(width: 100, alignment: .leading)
            VStack(alignment: .leading, spacing: 5) {
                Text(section.instructor ?? "Instructor not listed")
                Text("\((section.days ?? []).joined(separator: "/")) · \(section.start ?? "TBA")–\(section.end ?? "TBA")").font(.callout).foregroundStyle(.secondary)
            }.frame(maxWidth: .infinity, alignment: .leading)
            VStack(alignment: .trailing, spacing: 5) {
                if let rating = section.rating?.rating {
                    let label = "★ \(String(format: "%.1f", rating)) · \(section.rating?.source?.lowercased() == "rmp" ? "RMP" : section.rating?.source ?? "source unavailable")"
                    if let url = safeWebURL(section.rating?.url) { Link(label, destination: url) } else { Text(label) }
                } else { Text("No rating").foregroundStyle(.secondary) }
                if let seats = section.seats { Text("\(seats.open.map(String.init) ?? "?")/\(seats.capacity.map(String.init) ?? "?") seats open").foregroundStyle(.secondary) }
                else { Text("Seats unavailable").foregroundStyle(.secondary) }
            }.font(.callout)
        }.padding(.vertical, 9)
    }
}
