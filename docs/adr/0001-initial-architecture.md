# 0001 — 初期 iOS アーキテクチャ

## Status

Accepted

## Context

GitHub Template Repository から SwiftUI アプリを繰り返し立ち上げる。利用者はアプリ名、Bundle ID、対応デバイス、最低 OS を選び、ローカルで再現可能なビルドとテストを実行する。Claude Code の共通ルールは各プロダクトの説明と独立して保守する。

## Decision

- Xcode のプロジェクトと共有スキームは XcodeGen で生成する。ターゲット、依存、ビルド設定を YAML でレビューでき、bootstrap でアプリ固有の設定を更新できる。bootstrap は初期化の完了後に自身と回帰テストを削除し、アプリのリポジトリにテンプレートの保守用ファイルを残さない。
- 署名の Team ID は `project.yml` の `DEVELOPMENT_TEAM` で管理する。`.xcodeproj` は再生成するため、Xcode の画面で選んだチームは保持されない。Team ID は秘密情報ではないため、プロジェクト定義に含めてよい。
- Feature-first と軽量 MVVM を組み合わせる。小さな機能のコードを一箇所で追え、状態管理が複雑になったときに Observation の ViewModel を加えられる。
- 依存は Composition Root で組み立て、Initializer Injection で渡す。SwiftUI Environment は共有状態に限って使う。外部 DI ライブラリを追加するコストに見合う登録やライフサイクル管理は初期段階では必要ない。
- 永続化はプロダクトのデータ量、同期、移行要件が判明してから選ぶ。初期段階でデータモデルや移行方針を拘束しない。
- mise の Aqua バックエンドで XcodeGen と SwiftLint を固定する。両ツールの公式リリースを共通コマンドでインストールできる。swift-format は Xcode 同梱版を利用し、コンパイラと同じツールチェーンに揃える。[mise Registry](https://mise.jdx.dev/registry.html)、[swift-format](https://github.com/swiftlang/swift-format)
- Xcode は 2026年11月22日時点の最新安定版である 27.2 に固定する。Swift 6.4 と iOS 27.2 SDK を含み、テンプレートの Swift 6 言語モードと iOS 26.0 の Deployment Target を満たす。macOS Tahoe 26.6 以降を必要とする。開発に使う Mac の Xcode と揃え、テンプレートから作るアプリが App Store の SDK 要件の引き上げに追随しやすくする。Deployment Target は Xcode と独立しており、iOS 26.0 のまま変えない。swift-format が Xcode に同梱されるため、整形結果を揃える目的でバージョンは完全一致で固定する。GitHub Actions では Xcode 27.2 がプレビューの `xcode-27` イメージにのみ含まれ、`macos-26` イメージの既定は Xcode 26.6 である。CI を整備する際にイメージを選定する。[Apple の SDK とシステム要件](https://developer.apple.com/xcode/system-requirements/)、[Xcode 26.6](https://developer.apple.com/documentation/xcode-release-notes/xcode-26_6-release-notes)、[Xcode 27.2](https://developer.apple.com/documentation/xcode-release-notes/xcode-27_2-release-notes)、[GitHub Actions runner イメージ](https://github.com/actions/runner-images#available-images)
- 初期値は iPhone と iOS 26.0、言語モードは Swift 6 とする。Unit Test に Swift Testing、起動確認に XCUITest を使う。swift-format は整形、SwiftLint は少数の品質ルールを担当する。
- Claude Code の設定は `CLAUDE.md` と共通 Rules で管理する。Git は trunk-based とし、短命ブランチの PR を Squash Merge する。

## Consequences

- クローン後と `project.yml` を変えたときに再生成が必要になる。共有設定を Xcode の UI で試した場合は、プロジェクト定義へ反映する。
- 依存が増えると Composition Root の組み立ても増える。機能分割や共通化は利用箇所が見えてから行う。
- 永続化を導入するプロダクトは、ストレージ選定と移行テストを追加する。
- Xcode のインストールと選択は手動で行う。Xcode を更新する際は同梱の swift-format と Simulator の互換性も確認する。`.xcode-version` と `project.yml` の `options.xcodeVersion` を合わせて更新し、Xcode が提示する推奨設定は `project.yml` に反映する。
