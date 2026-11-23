# iOS App Template

個人開発向けの SwiftUI スターターです。生成した Xcode プロジェクトでアプリをビルドし、Swift Testing と XCUITest を実行できます。初期値は StarterApp、`com.example.starterapp`、iPhone、iOS 26.0 です。

## テンプレートから新規アプリを作る

次の順に進めます。Ruleset を設定すると `main` へ直接 push できなくなるため、初期化結果の push を先に行います。

1. リポジトリを作成してクローンします。GitHub で **Use this template → Create a new repository** を選ぶか、CLI で作成します。Private リポジトリでは、macOS Runner の実行が GitHub Actions の利用枠を消費します。

   ```sh
   gh repo create <REPOSITORY> --template shiba-tt/ios-app-template --private --clone
   cd <REPOSITORY>
   ```

2. [開発環境](#開発環境)をセットアップします。
3. クローンしたリポジトリのルートで初期化します。初期化には Python 3 を使います。追加の Python パッケージは不要です。

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
     --deployment-target "26.0" \
     --team-id "ABCDE12345"
   ```

4. 生成された `.xcodeproj` を開き、[ビルドとテスト](#ビルドとテスト)を実施します。CLI では次のコマンドで全検証を実行できます。

   ```sh
   mise exec -- ./scripts/check.sh "$(./scripts/select_simulator.py --runtime 27.2)"
   ```

5. 初期化による変更と `.bootstrap-complete` をコミットし、`main` に push します。

   ```sh
   git add -A
   git commit -m "chore: initialize app from template"
   git push origin main
   ```

6. GitHub Actions の [CI](#ci) が成功したことを確認します。

   ```sh
   gh run list --branch main --limit 1
   ```

7. [GitHub Ruleset](#github-ruleset) を設定します。Ruleset はテンプレートからコピーされません。
8. リポジトリで `claude` を起動してフォルダを信頼し、[Claude Code ハーネス](#claude-code-ハーネス)の手順で最初の機能を開発します。

`--app-name` は Xcode の内部名です。画面上のアイコンラベルには `--display-name` を使います。省略時は内部名が使われます。対応デバイスは `iphone` または `universal`（iPhone と iPad）です。対話モードでは iPhone と iOS 26.0 が既定値です。全オプションは `./scripts/bootstrap.sh --help` で確認できます。

`--team-id` は実機ビルドに使う Apple Developer の Team ID で、10 文字の英大文字と数字です。省略した場合は、後から `project.yml` の `DEVELOPMENT_TEAM` に設定します。

Deployment Target はプロジェクトごとに設定できます。bootstrap は `major.minor` 形式を受け付けます。major は正の整数、minor は 0 以上の整数で、各数値を先頭の 0 で桁埋めしません。`27.0` のような値も指定できます。指定したバージョンで開発するには、対応する Xcode、SDK、Simulator ランタイムを用意し、ビルドとテストで確認してください。

初期化では、設定と Xcode プロジェクトを一時領域で準備し、生成に成功してから反映します。同じ名前の `.xcodeproj` がすでにある場合は、別の場所に移動してから実行してください。反映後は bootstrap のスクリプトと回帰テストを削除し、README の「開発環境」より前にあるテンプレート向けの説明をアプリの概要に置き換えます。初期化済みのリポジトリでは、以後の設定変更を `project.yml` で行います。

### 初期化が中断されたとき

`.bootstrap-in-progress` が残っている場合は、実行中の bootstrap がないことを確認してください。`.bootstrap-complete` があれば設定の反映は完了しています。残った一時領域を別の場所へ移動できます。

完了マーカーがなく反映途中だった場合は、`.bootstrap-in-progress/backup/` の原本を確認します。反映前に作成する原本は `project.yml`、`App/AppEntry.swift`、`README.md`、`CLAUDE.md` です。反映が始まっていた場合は原本を戻し、生成された対象の `.xcodeproj` と一時領域を別の場所へ移動してから再実行してください。原本が揃う前に止まった場合は、反映開始前の状態です。

### bootstrap の回帰テスト

テンプレートを変更したときは、初期化前のチェックアウトで次のコマンドを実行します。テストはテンプレートを一時ディレクトリにコピーし、XcodeGen のスタブを使って初期化、入力エラー、失敗時の復旧を検証します。

```sh
python3 -m unittest discover -s scripts/tests -p 'test_*.py' -v
```

実際のプロジェクト生成は、新規クローンで bootstrap を実行するか、既存の設定で `mise exec -- xcodegen generate` を実行して確認します。CI は同じ回帰テストに加え、一時ディレクトリで別のアプリ名と Bundle ID に初期化し、実際の XcodeGen で生成できることを確認します。

## 開発環境

- `.xcode-version` に記載した Xcode 27.2 と、macOS Tahoe 26.6 以降。[Xcode 27.2 リリースノート](https://developer.apple.com/documentation/xcode-release-notes/xcode-27_2-release-notes)
- Xcode の Settings → Components で iOS Simulator ランタイムをインストールしてください。
- mise。[mise セットアップ](https://mise.jdx.dev/getting-started.html)

Xcode を起動して初回セットアップを済ませ、表示されるバージョンが `.xcode-version` と一致することを確認します。

```sh
xcodebuild -version
```

一致しない場合は、`xcode-select` で固定した Xcode を選ぶか、インストール先に合わせて `DEVELOPER_DIR` を設定してから、もう一度確認します。

```sh
export DEVELOPER_DIR=/Applications/Xcode_27.2.app/Contents/Developer
```

バージョンが一致したら、固定したツールをインストールします。

```sh
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
- 実機で実行するときは、`settings.base` の `DEVELOPMENT_TEAM` に Apple Developer の Team ID を設定します。`.xcodeproj` は再生成されるため、Xcode の Signing & Capabilities で選んだチームは保持されません。
- Xcode が **Update to recommended settings** を表示した場合は **Perform Changes** を実行せず、提案された設定を `project.yml` に反映して再生成します。Xcode を更新するときは、`.xcode-version` と `options.xcodeVersion` を同じバージョンに変更します。

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

## CI

GitHub Actions の [CI](.github/workflows/ci.yml) は、Pull Request、`main` への push、手動実行で動きます。設計判断は [ADR 0002](docs/adr/0002-ios-ci-foundation.md) に記録しています。

| ジョブ | Runner | Pull Request | `main` への push | 手動 quick | 手動 full |
| --- | --- | --- | --- | --- | --- |
| `quality-and-security`：Python / Shell 構文、actionlint、zizmor、テンプレートの回帰テスト、Claude Code ハーネスのテスト | `ubuntu-24.04` | 実行 | 実行 | 実行 | 実行 |
| `ios-build-and-unit-tests`：swift-format、SwiftLint、XcodeGen、ビルド、Swift Testing | `xcode-27` | 実行 | 実行 | 実行 | 実行 |
| `ios-ui-tests`：XcodeGen、ビルド、XCUITest | `xcode-27` | スキップ | 実行 | スキップ | 実行 |

同じ Pull Request に新しいコミットを push すると、古い実行だけをキャンセルします。`main` への push と手動実行はキャンセルしません。

手動実行は、ワークフローがデフォルトブランチに存在するようになると使えます。PR のブランチも指定できます。

```sh
gh workflow run ci.yml --ref <BRANCH> -f mode=full
```

### ローカルでの検証

Pull Request と同じ Swift の検証は `--tests unit`、UI Test まで含める場合はオプションなしで実行します。

```sh
destination="$(./scripts/select_simulator.py --runtime 27.2)"
mise exec -- ./scripts/check.sh --tests unit "$destination"
mise exec -- ./scripts/check.sh "$destination"
mise exec -- actionlint
mise exec -- zizmor .
```

### CI が失敗したとき

1. GitHub の **Actions** で失敗したステップのログを確認します。`Show toolchain` と `Select iOS Simulator` に、使用した Xcode、機種、Runtime、UDID が出力されます。
2. 失敗した macOS ジョブの診断情報を取得します。Artifact は失敗時のみ作成され、7 日間保持されます。

   ```sh
   gh run download <RUN_ID> --name ios-build-and-unit-tests-diagnostics-<RUN_ATTEMPT>
   ```

3. `build.log`、`test-*.log`、`environment.txt` を確認します。`.xcresult` は Xcode で開くか、CLI で要約を表示します。UI Test のスクリーンショットも `.xcresult` に含まれます。

   ```sh
   xcrun xcresulttool get test-results summary --path test-unit.xcresult
   ```

4. Xcode が見つからないエラーは、`.xcode-version` と [Runner イメージ](https://github.com/actions/runner-images#available-images)の内容を比較します。CI は別の Xcode や iOS Runtime に切り替えません。Xcode を更新するときは `.xcode-version`、`project.yml` の `options.xcodeVersion`、`ci.yml` の `IOS_SIMULATOR_RUNTIME` を揃えます。

### GitHub Ruleset

CI の成功を確認してから、GitHub の **Settings → Rules → Rulesets** で `main` に次の設定を人が適用します。Ruleset はテンプレートからコピーされないため、リポジトリごとに設定します。

- Pull Request を必須にし、他者の Approve は必須にしません。
- 必須ステータスチェックは `quality-and-security` と `ios-build-and-unit-tests` です。`ios-ui-tests` は Pull Request で実行しないため含めません。
- Squash Merge を基本にします。

## Claude Code ハーネス

Claude Code に機能開発を依頼したときに、規約に沿った実装、検証、PR 作成、レビューを同じ手順で進めるための設定です。初期化後のアプリでもそのまま使えます。初回は `claude` を対話起動してフォルダを信頼してください。

| Skill | 用途 | 起動 |
| --- | --- | --- |
| `implement-feature` | 機能の実装とテスト追加 | 手動・自動 |
| `verify-ios` | `quick`（Unit Test まで）/ `full`（UI Test まで）の検証 | 手動・自動 |
| `prepare-pr` | commit、push、PR 作成、CI 確認 | 手動のみ |
| `review-pr` | `pr-reviewer` Subagent による読み取り専用レビュー | 手動のみ |

```text
設定画面を追加して
/verify-ios quick
/prepare-pr
/review-pr 123
```

- **権限**：コード編集と指定した検証は自動で実行します。commit、push、PR 作成、依存の追加は承認が必要です。force push、PR のマージ、機密情報の読み取りは拒否します。
- **Hooks**：Swift ファイルの編集後に `swift-format lint` の結果を伝え、読み取り専用以外の Git / GitHub 操作に承認を求めます。コードの書き換えやビルドは行いません。
- **CI**：`quality-and-security` がハーネスの設定と Hook をテストします。Claude Code 本体は起動しないため、実際の動作は手動スモークテストで確認します。

詳しい手順と制御の限界は [Claude Code ハーネス](docs/claude-harness.md)、設計判断は [ADR 0003](docs/adr/0003-claude-code-harness.md) を参照してください。

## 構成

| パス | 内容 |
| --- | --- |
| `App/AppEntry.swift` | SwiftUI のエントリポイントと Composition Root |
| `App/Features/Home/` | 起動画面 |
| `Tests/Unit/`、`Tests/UI/` | Swift Testing と XCUITest |
| `scripts/check.sh` | ローカルと CI の共通検証 |
| `scripts/select_xcode.sh`、`scripts/select_simulator.py` | CI の Xcode と Simulator の選択 |
| `.github/` | GitHub Actions、Dependabot、actionlint の設定 |
| `CLAUDE.md`、`.claude/rules/` | プロダクト情報と共通開発ルール |
| `.claude/skills/`、`.claude/agents/` | Claude Code の作業手順とレビュー用 Subagent |
| `.claude/hooks/`、`.claude/settings.json` | 軽量 Hook と権限設定 |
| `.claude/tests/` | ハーネスのテスト |
| `docs/adr/` | 設計判断の記録 |

## 開発とライセンス

`main` を安定ブランチとし、短命ブランチから PR を作り、Squash Merge します。配布、永続化、アプリアイコンはプロダクトに合わせて追加します。

テンプレート由来コードを再利用・配布する場合は、著作権表示と許諾文を含む [MIT ライセンス](LICENSE)を保持してください。
