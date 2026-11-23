# CLAUDE.md

## アプリ概要

StarterApp は SwiftUI の iOS スターターです。初期 Bundle ID は `com.example.starterapp`、対象は iPhone、Deployment Target は iOS 26.0 です。

## 開発

- SwiftUI、Swift 6、XcodeGen、Swift Testing、XCUITest を使います。固定 Xcode を選び、README に従って `mise trust` と `mise install` を実行します。
- `App/AppEntry.swift` が起点で、機能は `App/Features/`、テストは `Tests/Unit/` と `Tests/UI/` に置きます。
- `mise exec -- xcodegen generate` でプロジェクトを生成します。設定変更は `project.yml` に反映します。
- `mise exec -- ./scripts/check.sh 'platform=iOS Simulator,id=<SIMULATOR_UDID>'` でフォーマット、Lint、ビルド、両テストを検証します。個別の Lint は `mise exec -- swiftlint lint --strict` です。
- 機能内に変更を閉じ、依存の組み立てはアプリの起点に集めます。詳細は [設計](.claude/rules/architecture.md)、[Swift](.claude/rules/swift.md)、[テスト](.claude/rules/testing.md) の共通ルールを参照してください。

## Claude Code ハーネス

- 機能開発は `implement-feature`、検証は `verify-ios` の `quick` / `full` を使います。PR 作成の `/prepare-pr` とレビューの `/review-pr` は、利用者が起動したときだけ使います。
- commit、push、PR 作成、依存の追加は利用者の承認を得てから行います。PR はマージしません。
- 運用手順は [Claude Code ハーネス](docs/claude-harness.md) を参照してください。
