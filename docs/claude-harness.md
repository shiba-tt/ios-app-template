# Claude Code ハーネス

Claude Code に機能開発を依頼したときに、既存の規約に沿った実装、検証、PR 作成、レビューを同じ手順で進めるための設定です。設計判断は [ADR 0003](adr/0003-claude-code-harness.md) に記録しています。

## 使い方

```text
設定画面を追加して          # implement-feature が自動で使われる
/implement-feature 設定画面を追加して
/verify-ios quick
/verify-ios full
/prepare-pr
/review-pr 123
```

通常は、実装を依頼し、結果を確認してから `/prepare-pr`、`/review-pr` の順に実行します。

初回は、リポジトリで `claude` を対話起動してフォルダを信頼してください。信頼するまで `.claude/settings.json` の `allow` は適用されず、検証コマンドでも確認が表示されます。

## Skills

| Skill | 用途 | 起動 | 変更する範囲 |
| --- | --- | --- | --- |
| `implement-feature` | 機能の実装とテスト追加 | 手動・自動 | ローカルのコード |
| `verify-ios` | `quick` / `full` の検証 | 手動・自動 | なし |
| `prepare-pr` | commit、push、PR 作成、CI 確認 | 手動のみ | 承認された Git 操作 |
| `review-pr` | PR の独立レビュー | 手動のみ | なし |

### 検証モード

| モード | swift-format | SwiftLint | XcodeGen | Build | Unit Test | UI Test |
| --- | --- | --- | --- | --- | --- | --- |
| `quick` | 実行 | 実行 | 実行 | 実行 | 実行 | SKIP |
| `full` | 実行 | 実行 | 実行 | 実行 | 実行 | 実行 |

どちらも `scripts/check.sh` を使います。iOS Runtime は `ci.yml` の `IOS_SIMULATOR_RUNTIME` から取得し、見つからない場合は別の Runtime に切り替えず失敗を報告します。

### PR 作成

`/prepare-pr` は差分、機密情報、テスト、検証結果を確認し、commit、push、PR の内容を提示します。承認された操作だけを実行し、PR 作成後は最新コミットの CI を確認します。

CI が失敗した場合は、ログから原因を切り分けてローカルで修正します。追加の commit と push の前に再度承認を求めます。修正の試行は 2 回までで、PR のマージは行いません。

### PR レビュー

`/review-pr` は `pr-reviewer` Subagent を独立したコンテキストで起動します。引数には PR 番号または URL を指定します。省略すると現在のブランチの PR を対象にし、特定できなければエラーになります。

レビューでは PR の差分、変更前後のコード、呼び出し元、関連テスト、規約を確認します。結果は次の形式です。

```markdown
### [High] 指摘の要約
- 対象：`App/Features/Example/ExampleView.swift:42`
- 問題：何が問題か
- 発生条件：実際に問題になる条件
- 根拠：コードから確認できた事実
- 推奨修正：修正方法
```

Severity は Critical、High、Medium、Low です。問題がなければ「指摘なし」と出力します。レビュー結果を PR に投稿する場合は、内容を確認して人が行います。

## 権限

共有設定は `.claude/settings.json`、個人設定は Git 管理外の `.claude/settings.local.json` に置きます。

| 操作 | 扱い |
| --- | --- |
| コードの参照、`App/`、`Tests/`、`docs/` の編集 | 自動許可 |
| Git の参照、指定した Lint / Build / Test、PR と CI の参照 | 自動許可 |
| commit、push、PR の作成・編集、コメント、依存追加 | 承認必須 |
| `project.yml`、`mise.toml`、`scripts/`、`.github/`、`.claude/`、`CLAUDE.md` の編集 | 承認必須 |
| force push、`git reset --hard`、`git clean`、PR のマージ、`sudo`、`rm -rf` | 拒否 |
| `.env`、署名鍵、SSH や GitHub の認証情報の読み取り | 拒否 |

### 制御の限界

- 権限ルールはコマンドの文字列で照合します。`PreToolUse` Hook がコマンドを解析し、`git -C . push`、`gh -R owner/repo pr merge`、`sh -c 'git push'` などの迂回も承認対象にしますが、任意のプログラムから実行される操作までは検出できません。
- `deny` は Claude が認識するファイル読み取りを止めますが、任意のプロセスが開くファイルまでは止められません。強い隔離が必要な場合は Claude Code の Sandbox を併用してください。
- `check.sh` は編集後のアプリとテストのコードを実行します。Simulator はセキュリティ境界ではありません。
- auto モードでは Subagent の `permissionMode` が無視されます。`pr-reviewer` の読み取り専用は、利用可能なツールの限定と Bash の許可リスト Hook で維持します。

## Hooks

| イベント | 対象 | 処理 |
| --- | --- | --- |
| `PostToolUse` | `App/`、`Tests/` の Swift ファイル | `swift-format lint` の結果を Claude に伝える。修正やブロックはしない |
| `PreToolUse` | Bash | コマンドを解析し、読み取り専用の一覧にない `git` / `gh` 操作に承認を要求する。`git add`、`git fetch`、`git switch` も対象 |
| `PreToolUse`（`pr-reviewer` のみ） | Bash | 読み取り専用の `git` / `gh` 以外を拒否する。環境変数を読める `--jq` と、別リポジトリを指定できる URL も拒否する |

Hook は Xcode のビルドやテストを実行しません。実行時間に上限があり、再試行もしません。

## テスト

```bash
python3 -m unittest discover -s .claude/tests -p 'test_*.py' -v
```

このテストは Skills、Subagent、設定、Hook の入出力を検証し、CI の `quality-and-security` でも実行されます。Claude Code 本体は起動せず、API キーも使いません。

CI の成功は、Claude Code が Skill や権限を実際に期待どおり解釈することまでは保証しません。ハーネスを変更したら、次の手動スモークテストを実施します。push や PR を伴う確認は、リモートを持たない一時リポジトリで行います。

- [ ] `/implement-feature` を起動でき、機能実装の依頼でも自動で使われる
- [ ] `/verify-ios quick` と `/verify-ios full` が実行内容どおりに結果を報告する
- [ ] `/prepare-pr` は手動でのみ起動し、commit、push、PR 作成の前に承認を求める
- [ ] `/review-pr <番号>` が `pr-reviewer` に委任され、書き込み系の操作が拒否される
- [ ] Swift ファイルの編集後に Hook が動き、ファイルを書き換えない
- [ ] `git push` と `git -C . push` で承認が求められる

## 新しいアプリでの利用

テンプレートから生成したアプリには、Skills、Subagent、Hooks、設定、テストがそのまま残ります。アプリ名や Bundle ID は `project.yml` と `CLAUDE.md` で管理するため、ハーネス側の変更は不要です。

アプリ固有の規約は `CLAUDE.md` や `.claude/rules/` に追加し、固有の作業手順は Skill として追加します。テンプレートの更新は自動では反映されないため、必要な変更を各アプリへ取り込みます。
