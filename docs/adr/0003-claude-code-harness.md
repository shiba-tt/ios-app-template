# 0003 — Claude Code 開発ハーネス

## Status

Accepted

## Context

Claude Code に iOS アプリの機能開発を依頼したときに、既存の規約に沿った実装、検証、PR 作成、レビューを再現できるようにする。ハーネスはテンプレートから生成した各アプリにもコピーされ、初期化後も動作する必要がある。自律実行の快適さより、意図しない外部への変更を防ぐことを優先する。

## Decision

- **4 Skills への分離**：`implement-feature`、`verify-ios`、`prepare-pr`、`review-pr` に責務を分ける。実装と検証は自動起動を許可し、外部に影響する PR 作成と、明示的に依頼するレビューは `disable-model-invocation` で手動起動に限定する。
- **レビューの Subagent 化**：`review-pr` は `context: fork` で `pr-reviewer` に委任する。実装時の会話から独立させ、PR の差分と関連コードだけを根拠にする。ツールを読み取り系に限定し、Bash は専用 Hook の許可リストで単一の `git` / `gh` 読み取りコマンドに制限し、環境変数を読める `--jq` と別リポジトリを指せる URL は許可しない。親が auto などのモードだと `permissionMode` は無視されるため、Hook を主な制御とする。
- **Quick / Full の 2 段階検証**：日常の区切りは Unit Test までの Quick、UI 変更の重点確認やリリース前は XCUITest を含む Full とする。CI の PR と `main` の検証範囲に対応する。
- **Hooks の軽量化**：編集ごとの処理は 1 ファイルの `swift-format lint` だけとし、修正もブロックもしない。編集途中の構文エラーで作業を止めず、Hook の連鎖も起こさない。ビルドとテストは `verify-ios` で実行する。
- **Git 操作の承認**：commit、push、PR 作成は `ask` ルールで承認を求める。ルールは文字列の前方一致で `git -C . push` などに一致せず、auto モードでは分類器が push を許可し得る。このため、コマンドをトークン解析し、読み取り専用の一覧にない `git` / `gh` 操作に承認を強制する `PreToolUse` Hook を追加する。force push やマージなどは `deny` にする。実行基盤を変える `project.yml`、`mise.toml`、`scripts/`、`.github/`、`.claude/` の編集も承認対象とする。
- **既存 CI の再利用**：検証は `scripts/check.sh` と `select_simulator.py` を使い、Runtime は `ci.yml` を設定元にする。ハーネスのテストは `.claude/tests/` に置き、既存の `quality-and-security` ジョブで実行する。Claude Code 本体と API キーは CI で使わない。
- **各アプリへのコピー**：共通ハーネスはアプリ名や Bundle ID を持たず、初期化で削除されるファイルに依存しない。専用リポジトリや自動同期は導入せず、アプリ固有の内容は `CLAUDE.md` と Rules に置く。

## Consequences

- 権限ルールと承認 Hook は文字列の検査であり、任意のプログラムからの操作は防げない。強い隔離が必要な場合は Sandbox を併用する。
- CI は設定とスクリプトの正しさを検証するが、Claude Code の実際の解釈は保証しない。ハーネスの変更時は手動スモークテストが必要である。
- 共有設定の `allow` は、利用者がフォルダを信頼するまで適用されない。
- テンプレートのハーネスを更新しても、生成済みのアプリには自動で反映されない。
- 将来 PR 修正の自律ループへ拡張する場合も、再 push の承認と試行回数の上限を維持する。必要になった時点で、承認の範囲と停止条件を別の ADR で定める。
