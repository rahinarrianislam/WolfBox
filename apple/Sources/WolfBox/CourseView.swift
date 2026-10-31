import SwiftUI
import WolfBoxCore

struct CourseView: View {
    @Bindable var model: AppModel
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 28) {
                HStack(alignment: .top) {
                    PageHeading(title: "Your course, caught up.", subtitle: "CSC 116 · Specifications, deadlines, and what changed.")
                    Button { Task { await model.syncCourse() } } label: { Label(model.busy.contains("sync") ? "Syncing…" : "Sync now", systemImage: "arrow.triangle.2.circlepath") }.buttonStyle(.borderedProminent).controlSize(.large).disabled(model.busy.contains("sync"))
                }
                HStack(alignment: .top, spacing: 32) {
                    VStack(alignment: .leading, spacing: 20) {
                        SectionHeading(title: "Since your last sync")
                        if model.busy.contains("sync") { ProgressView("Checking the course site and preparing documents…").controlSize(.small) }
                        if let job = model.syncJob {
                            Text("\((job.new ?? []).count) new · \((job.changed ?? []).count) changed · \(job.unchanged ?? 0) unchanged").font(.callout).foregroundStyle(.secondary)
                            ForEach(job.new ?? [], id: \.self) { id in update(id, isNew: true) }
                            ForEach(job.changed ?? [], id: \.self) { id in update(id, isNew: false) }
                            ForEach(Array((job.errors ?? []).enumerated()), id: \.offset) { _, issue in Text("\(issue.item ?? "Document"): \(issue.error ?? "Could not sync")").foregroundStyle(Color.wolfRed) }
                            if (job.new ?? []).isEmpty && (job.changed ?? []).isEmpty && (job.errors ?? []).isEmpty { Text("You’re up to date.") }
                        } else { Text("Sync to check for new assignments and changes to your course documents.").foregroundStyle(.secondary) }
                    }.frame(maxWidth: .infinity, alignment: .leading)
                    VStack(alignment: .leading, spacing: 18) {
                        SectionHeading(title: "This week")
                        let week = model.deadlines.filter { value in
                            guard let due = value.due.flatMap({ ISO8601DateFormatter().date(from: $0) }) else { return false }
                            return due >= Date() && due <= Date().addingTimeInterval(7 * 86400)
                        }
                        if week.isEmpty { Text("No deadlines in the next seven days.").foregroundStyle(.secondary) }
                        ForEach(Array(week.enumerated()), id: \.offset) { _, deadline in
                            VStack(alignment: .leading, spacing: 6) {
                                Text(deadline.what ?? "Assignment due").fontWeight(.medium)
                                Text(friendlyDate(deadline.due)).foregroundStyle(.secondary).font(.callout)
                            }
                        }
                        if model.deadlines.count > week.count {
                            DisclosureGroup("All upcoming deadlines") {
                                ForEach(Array(model.deadlines.enumerated()), id: \.offset) { _, deadline in
                                    VStack(alignment: .leading, spacing: 4) { Text(deadline.what ?? "Deadline"); Text(friendlyDate(deadline.due)).font(.caption).foregroundStyle(.secondary) }.padding(.vertical, 6)
                                }
                            }
                        }
                    }.padding(22).frame(width: 285, alignment: .leading).background(Color.wolfSurface, in: RoundedRectangle(cornerRadius: 8))
                }
                VStack(alignment: .leading, spacing: 14) {
                    SectionHeading(title: "Course library", detail: "\(model.docs.count) documents")
                    if model.docs.isEmpty { ContentUnavailableView("No documents yet", systemImage: "books.vertical", description: Text("Sync your course to bring its documents into your box.")) }
                    ForEach(model.docs) { doc in
                        Button { Task { await model.readDoc(doc) } } label: {
                            HStack(alignment: .top, spacing: 16) {
                                Image(systemName: doc.type == "assignment" ? "doc.text" : "book.closed").font(.title2).foregroundStyle(Color.wolfGreen).frame(width: 28)
                                VStack(alignment: .leading, spacing: 6) { Text(doc.title ?? doc.doc_id).font(.body.weight(.semibold)); Text(doc.summary ?? "Open to read this document.").foregroundStyle(.secondary).lineLimit(2) }
                                Spacer(); Text("v\(doc.version ?? 1)").font(.callout).foregroundStyle(.secondary); Image(systemName: "chevron.right").foregroundStyle(.tertiary)
                            }.padding(18).frame(maxWidth: .infinity, alignment: .leading).background(Color.wolfSurface, in: RoundedRectangle(cornerRadius: 6))
                        }.buttonStyle(.plain).disabled(model.busy.contains("document"))
                    }
                }
            }.padding(30)
        }
        .sheet(isPresented: Binding(get: { model.document != nil }, set: { if !$0 { model.document = nil } })) { DocumentReader(model: model) }
    }
    func update(_ id: String, isNew: Bool) -> some View {
        let doc = model.docs.first { $0.doc_id == id }
        return VStack(alignment: .leading, spacing: 10) {
            HStack { Text(doc?.title ?? id).font(.headline); Spacer(); Text(isNew ? "New" : "Updated").font(.callout.weight(.medium)).foregroundStyle(Color.wolfGreen) }
            Text(doc?.summary ?? "Open the document for details.").lineSpacing(4)
            if let note = doc?.change_note { Text(note).fontWeight(.medium).lineSpacing(4) }
            if let doc { Button("Read document") { Task { await model.readDoc(doc) } }.buttonStyle(.link) }
        }.padding(20).background(isNew ? Color.wolfGreen.opacity(0.08) : Color.wolfGold.opacity(0.14), in: RoundedRectangle(cornerRadius: 8))
    }
}
struct DocumentReader: View {
    @Bindable var model: AppModel
    @Environment(\.dismiss) private var dismiss
    var body: some View {
        VStack(spacing: 0) {
            HStack { Text(model.document?.doc?.title ?? "Course document").font(.title2.weight(.semibold)); Spacer(); Button("Done") { dismiss() }.keyboardShortcut(.cancelAction) }.padding(24)
            Divider()
            ScrollView {
                VStack(alignment: .leading, spacing: 22) {
                    if let summary = model.document?.doc?.summary { Text(summary).font(.title3).lineSpacing(5).padding(20).frame(maxWidth: .infinity, alignment: .leading).background(Color.wolfGreen.opacity(0.08), in: RoundedRectangle(cornerRadius: 6)) }
                    if let note = model.document?.doc?.change_note { Label(note, systemImage: "pencil.line").foregroundStyle(.secondary) }
                    MarkdownText(text: model.document?.text ?? "This document has no extracted text.")
                }.padding(30)
            }
        }.frame(width: 760, height: 700).background(Color.wolfPaper)
    }
}
