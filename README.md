# iOS App Template

個人開発向けの SwiftUI スターターです。生成した Xcode プロジェクトでアプリをビルドし、Swift Testing と XCUITest を実行できます。初期値は StarterApp、`com.example.starterapp`、iPhone、iOS 26.0 です。

## テンプレートから新規アプリを作る

1. GitHub で **Use this template → Create a new repository** を選び、生成したリポジトリをクローンします。
2. [開発環境](#開発環境)をセットアップし、クローンしたリポジトリのルートで初期化します。

   ```sh
   mise exec -- ./scripts/bootstrap.sh
   ```

   引数を指定すると、入力待ちなしで実行できます。

   ```sh
   mise exec -- ./scripts/bootstrap.sh \
     --app-name "BudgetMate" \
     --display-name "Budget Mate" \
     --bundle-id "com.example.budgetmate" \
     --platform iphone \
     --deployment-target "26.0"
   ```

3. 生成された `.xcodeproj` を開き、[ビルドとテスト](#ビルドとテスト)を実施します。設定変更と `.bootstrap-complete` をコミットします。

`--app-name` は Xcode の内部名です。画面上のアイコンラベルには `--display-name` を使います。省略時は内部名が使われます。対応デバイスは `iphone` または `universal`（iPhone と iPad）です。対話モードでは iPhone と iOS 26.0 が既定値です。全オプションは `./scripts/bootstrap.sh --help` で確認できます。

Deployment Target はプロジェクトごとに設定できます。bootstrap は `major.minor` 形式を受け付けます。major は正の整数、minor は 0 以上の整数で、各数値を先頭の 0 で桁埋めしません。`27.0` のような値も指定できます。指定したバージョンで開発するには、対応する Xcode、SDK、Simulator ランタイムを用意し、ビルドとテストで確認してください。

初期化では、設定と Xcode プロジェクトを一時領域で準備し、生成に成功してから反映します。同じ名前の `.xcodeproj` がすでにある場合は、別の場所に移動してから実行してください。初期化済みのリポジトリでは、以後の設定変更を `project.yml` で行います。

## 開発環境

- `.xcode-version` に記載した Xcode 27.2 と、macOS Tahoe 26.6 以降。[Xcode 27.2 リリースノート](https://developer.apple.com/documentation/xcode-release-notes/xcode-27_2-release-notes)
- Xcode の Settings → Components で iOS Simulator ランタイムをインストールしてください。
- mise と Python 3。Python は bootstrap とその回帰テストに使います。追加の Python パッケージは不要です。[mise セットアップ](https://mise.jdx.dev/getting-started.html)

Xcode を起動して初回セットアップを済ませ、対象の Xcode を選択します。複数バージョンがある場合はインストール先に合わせてパスを変更してください。

```sh
export DEVELOPER_DIR=/Applications/Xcode_27.2.app/Contents/Developer
xcodebuild -version
mise trust
mise install
```

`mise.toml` で XcodeGen と SwiftLint を固定しています。swift-format は固定した Xcode に同梱されている実行ファイルを `xcrun swift-format` で指定します。`.xcode-version` は使用バージョンの記録で、Xcode の選択は `DEVELOPER_DIR` または `xcode-select` で行います。

## プロジェクト生成と設定変更

```sh
mise exec -- xcodegen generate
```

生成された `.xcodeproj` を開き、同じ名前のスキームを選択します。Git で管理するプロジェクト定義は `project.yml` です。変更後は再生成してください。

- 名前とターゲットの対応は `name`、`targets`、`scheme.testTargets`、`dependencies` で管理します。内部名は二重引用符で囲みます。
- 表示名は `INFOPLIST_KEY_CFBundleDisplayName`、アプリとテストの Bundle ID は各ターゲットの `PRODUCT_BUNDLE_IDENTIFIER` です。
- 対応デバイスは `iOSDeviceFamily` の `TARGETED_DEVICE_FAMILY` で指定します。iPhone は `"1"`、Universal は `"1,2"` です。
- 最低 OS は `options.deploymentTarget.iOS`、Swift の言語モードは `SWIFT_VERSION` で指定します。Xcode 27.2 の SDK は iOS 27.2 です。Deployment Target を変更するときは、使用する API、Xcode が対応する Deployment Target、Simulator ランタイムを確認してください。[Apple の SDK とシステム要件](https://developer.apple.com/xcode/system-requirements/)

`com.example` 配下の Bundle ID は例示用です。実機配布や公開には、自分で管理する識別子と署名設定を使用してください。

## ビルドとテスト

Xcode で iOS Simulator を選び、**Product → Build** と **Product → Test** を実行できます。共有スキームに Unit Test と UI Test が含まれます。

CLI では、一覧に表示された Simulator の UDID を使って、フォーマット検証、Lint、プロジェクト生成、ビルド、テストをまとめて実行できます。

```sh
xcrun simctl list devices available
mise exec -- ./scripts/check.sh 'platform=iOS Simulator,id=<SIMULATOR_UDID>'
```

フォーマットの自動修正と個別のチェックも実行できます。

```sh
xcrun swift-format format --in-place --recursive App Tests
xcrun swift-format lint --strict --recursive App Tests
mise exec -- swiftlint lint --strict
```

swift-format がレイアウトと表記を扱い、SwiftLint は強制キャストや不適切な初期化などを検出します。Swift Concurrency の診断は Swift 6 コンパイラに従います。

### bootstrap の回帰テスト

初期化前のテンプレートのチェックアウトで次のコマンドを実行します。テストはテンプレートを一時ディレクトリにコピーし、XcodeGen のスタブを使って初期化、入力エラー、失敗時の復旧を検証します。Python 3 で実行できます。

```sh
python3 -m unittest discover -s scripts/tests -p 'test_*.py' -v
```

実際のプロジェクト生成は、新規クローンで bootstrap を実行するか、既存の設定で `mise exec -- xcodegen generate` を実行して確認します。

## 構成

| パス | 内容 |
| --- | --- |
| `App/AppEntry.swift` | SwiftUI のエントリポイントと Composition Root |
| `App/Features/Home/` | 起動画面 |
| `Tests/Unit/`、`Tests/UI/` | Swift Testing と XCUITest |
| `scripts/` | 初期化とローカル検証 |
| `CLAUDE.md`、`.claude/rules/` | プロダクト情報と共通開発ルール |
| `docs/adr/` | 設計判断の記録 |

## 初期化が中断されたとき

`.bootstrap-in-progress` が残っている場合は、実行中の bootstrap がないことを確認してください。`.bootstrap-complete` があれば設定の反映は完了しています。残った一時領域を別の場所へ移動できます。

完了マーカーがなく反映途中だった場合は、`.bootstrap-in-progress/backup/` の原本を確認します。反映前に作成する原本は `project.yml`、`App/AppEntry.swift`、`README.md`、`CLAUDE.md` です。反映が始まっていた場合は原本を戻し、生成された対象の `.xcodeproj` と一時領域を別の場所へ移動してから再実行してください。原本が揃う前に止まった場合は、反映開始前の状態です。

## 開発とライセンス

`main` を安定ブランチとし、短命ブランチから PR を作り、Squash Merge します。実機の署名、配布、CI、永続化、アプリアイコンはプロダクトに合わせて追加します。

テンプレート由来コードを再利用・配布する場合は、著作権表示と許諾文を含む [MIT ライセンス](LICENSE)を保持してください。
