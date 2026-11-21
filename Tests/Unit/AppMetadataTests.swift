import Foundation
import Testing

struct AppMetadataTests {
  @Test func hostAppDeclaresDisplayName() throws {
    #expect(Bundle.main.bundleURL.pathExtension == "app")
    let displayName = try #require(
      Bundle.main.object(forInfoDictionaryKey: "CFBundleDisplayName") as? String
    )
    #expect(!displayName.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
  }
}
