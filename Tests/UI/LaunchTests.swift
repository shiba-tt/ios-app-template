import XCTest

final class LaunchTests: XCTestCase {
  @MainActor
  func testLaunchShowsHome() {
    let app = XCUIApplication()
    app.launch()

    XCTAssertTrue(app.staticTexts["home.title"].waitForExistence(timeout: 5))
  }
}
