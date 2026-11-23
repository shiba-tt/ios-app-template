---
name: verify-ios
description: Use when iOS code changes reach a stopping point, before preparing a pull request, or when the user asks to run format, lint, build, unit tests, or UI tests (例：「検証して」「テストを実行して」).
argument-hint: "[quick|full]"
---

# verify-ios

モード：$ARGUMENTS

この Skill は検証だけを行い、コードを変更しません。失敗を見つけた場合は原因を報告し、修正は検証の外で行います。

## モード

| モード | 内容 | 使う場面 |
| --- | --- | --- |
| `quick`（既定） | swift-format、SwiftLint、XcodeGen、Build、Unit Test | 機能開発の区切り、`prepare-pr` の前 |
| `full` | `quick` と UI Test | UI 変更の重点確認、リリース前、ユーザーの依頼 |

モードが空なら `quick` を使います。`quick`、`full` 以外の値は実行せず、ユーザーに確認します。

ファイルを編集するたびには実行しません。前回の検証後にコードや設定を変更した場合は、結果が古いので再実行します。

## 手順

各コマンドは、下に示す形のまま単独で実行します。パイプ、リダイレクト、`echo $?` を付けると権限ルールに一致しません。成否は Bash ツールの終了状態で判定します。

1. `.github/workflows/ci.yml` の `IOS_SIMULATOR_RUNTIME` の値を読み、これを Runtime とする。読み取れない場合は環境不備として報告し、停止する。
2. Simulator を選択する。

   ```bash
   ./scripts/select_simulator.py --runtime <Runtime>
   ```

   失敗した場合は別の Runtime に切り替えず、環境不備として理由と導入済みの Runtime を報告する。

3. 標準出力の destination を一字一句そのまま使い、シングルクォートで囲んで検証を実行する。xcodebuild は時間がかかるため、Bash の timeout は 600000 ms を指定する。

   ```bash
   # quick
   mise exec -- ./scripts/check.sh --tests unit '<destination>'
   # full
   mise exec -- ./scripts/check.sh '<destination>'
   ```

4. 実行時の `git rev-parse --short HEAD` と、未コミットの変更の有無を記録する。
5. 下の形式で報告する。

## 結果の判定

`check.sh` は swift-format、SwiftLint、XcodeGen、Build、Test の順に実行し、最初の失敗で停止します。

- 実行して成功した項目だけを `PASS` にする。
- 失敗した項目を `FAIL` にする。
- 実行されなかった項目は、すべて `SKIP` にする。`quick` の UI Test は常に `SKIP` にする。
- `full` の Test ステップが失敗した場合は、出力の失敗テスト名からターゲットごとに判定する。判定できない項目は `FAIL` にして、備考に理由を書く。

失敗の種類を次のように分けます。

| 種類 | 例 |
| --- | --- |
| 環境不備 | Xcode の不一致、ツールや Runtime の不足、Simulator の起動失敗 |
| 品質チェック失敗 | swift-format、SwiftLint の指摘 |
| ビルド失敗 | コンパイルエラー、プロジェクト生成の失敗 |
| テスト失敗 | アサーション失敗、テストのクラッシュ、タイムアウト |

## 報告形式

```markdown
検証モード：quick / full
検証対象：<短い SHA>（未コミットの変更：あり / なし）
Simulator：<機種>、iOS <Runtime>

| チェック | 結果 | 備考 |
| --- | --- | --- |
| swift-format | PASS / FAIL / SKIP | |
| SwiftLint | PASS / FAIL / SKIP | |
| XcodeGen | PASS / FAIL / SKIP | |
| Build | PASS / FAIL / SKIP | |
| Unit Test | PASS / FAIL / SKIP | |
| UI Test | PASS / FAIL / SKIP | |
```

失敗がある場合は、表の後に失敗の種類、再現コマンド、分かっている原因を記載します。
