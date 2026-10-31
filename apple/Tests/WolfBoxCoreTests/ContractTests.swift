import XCTest
@testable import WolfBoxCore

final class ContractTests: XCTestCase {
    func testDocIDsAreOneEncodedPathSegment() throws {
        let url = try APIClient.makeURL(base: "http://127.0.0.1:8000", segments: ["api", "students", "alex", "docs", "csc116/hw4"])
        XCTAssertEqual(url.absoluteString, "http://127.0.0.1:8000/api/students/alex/docs/csc116%2Fhw4")
    }
    func testRejectsInvalidServerAndCredentialsInURL() {
        for base in ["file:///tmp", "http://a:b@localhost:8000", "not a url"] {
            XCTAssertThrowsError(try APIClient.makeURL(base: base, segments: ["api"]))
        }
    }
    func testRunWaitsForBothTestsAndHint() throws {
        let pending = try JSONDecoder().decode(Run.self, from: Data(#"{"run_id":"r1","status":"done","hint_status":"pending","new_field":true}"#.utf8))
        XCTAssertFalse(pending.isComplete)
        let done = try JSONDecoder().decode(Run.self, from: Data(#"{"run_id":"r1","status":"done","hint_status":"ready"}"#.utf8))
        XCTAssertTrue(done.isComplete)
    }
    func testCanvasFailsClosed() {
        XCTAssertFalse(CanvasAuthorization(authorized: false, role: "instructor").allows("publish_assignment"))
        XCTAssertFalse(CanvasAuthorization(authorized: true, role: "student").allows("publish_assignment"))
        XCTAssertFalse(CanvasAuthorization(authorized: true, role: "instructor").allows("unknown"))
        XCTAssertFalse(CanvasAuthorization(authorized: true, role: "student").allows("list_assignments"))
        XCTAssertFalse(CanvasAuthorization(authorized: true, role: "ta").allows("open_course"))
        XCTAssertTrue(CanvasAuthorization(authorized: true, role: "instructor").allows("list_assignments"))
        XCTAssertTrue(CanvasAuthorization(authorized: true, role: "instructor").allows("publish_assignment"))
    }
    func testCalendarPreservesActualTimesAndAllMeetings() throws {
        let sections = try JSONDecoder().decode([CourseSection].self, from: Data(#"[{"course":"A","days":["Mon","Wed"],"start":"09:35","end":"10:25"},{"course":"B","days":["Fri"],"start":"18:15","end":"19:30"}]"#.utf8))
        let layout = WeekLayout(sections: sections)
        XCTAssertEqual(layout.meetings.count, 3)
        XCTAssertEqual(layout.meetings.last?.start, 1095)
        XCTAssertGreaterThanOrEqual(layout.endMinute, 1170)
        XCTAssertEqual(WeekLayout.minutes("09:35"), 575)
    }
}

extension ContractTests {
    func testHeatmapAcceptsStudentListAndCount() throws {
        let listed = try JSONDecoder().decode(Heatmap.self, from: Data(#"{"students":["Student 1","Student 2"],"mistake_tags":{"off_by_one":4}}"#.utf8))
        XCTAssertEqual(listed.students, 2)
        let counted = try JSONDecoder().decode(Heatmap.self, from: Data(#"{"students":3}"#.utf8))
        XCTAssertEqual(counted.students, 3)
    }
}
