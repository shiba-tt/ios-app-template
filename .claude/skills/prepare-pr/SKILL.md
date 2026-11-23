---
name: prepare-pr
description: Use when the user explicitly runs /prepare-pr to commit reviewed changes, push the branch, open a GitHub pull request, and check its CI.
argument-hint: "[PR の補足情報]"
disable-model-invocation: true
---

# prepare-pr

補足情報：$ARGUMENTS

変更を整理して Pull Request を作成し、最新コミットの CI を確認します。PR のマージと、独立したコードレビューはこの Skill では行いません。`review-pr` はユーザーが別途起動します。

## 承認のルール

commit、push、PR 作成、PR の編集など、Git やリモートの状態を変える操作は、対象と内容を提示してユーザーの明示的な承認を得てから実行します。

- この Skill の起動は、これらの操作の承認ではありません。
- 承認は提示した内容に対してのみ有効です。内容が変わったら再度承認を得ます。
- 権限プロンプトが表示された場合は、それにも従います。

## 1. 事前確認

次を確認し、問題があれば停止して報告します。

1. 現在のブランチ。`main` の場合は、作業ブランチ名を提案し、承認後に作成する。
2. `git status --short`、ステージ済みの変更、未追跡ファイル。
3. `origin/main` との差分。意図しないファイルや無関係な変更がないか。
4. 差分に認証情報、秘密鍵、トークン、個人情報、`.env`、署名ファイルがないか。疑わしい値は報告に転記せず、ファイルと行だけを示す。
5. 変更に対応するテストの追加状況。
6. 現在の変更を対象にした `verify-ios` の結果。結果がない、または古い場合は `verify-ios` の `quick` を実行する。`FAIL` がある場合は PR 作成に進まない。

## 2. 承認を得る内容

次をまとめて提示し、実行してよい操作をユーザーに確認します。

- ブランチ名
- commit するファイルの一覧と commit メッセージ
- push 先
- PR のタイトルと本文
- 検証結果

ファイルは名前を指定してステージします。`git add -A` や `git add .` は使いません。既存のステージ内容と無関係な変更を尊重し、混ざる場合はユーザーに確認します。

## 3. PR 本文

次の見出しで作成します。該当がない項目は「なし」と書きます。

```markdown
## Summary
## Changes
## Architecture decisions
## Test results
## Risks / Known limitations
## Screenshots
## Review points
## Follow-up tasks
```

`Test results` には `verify-ios` の結果表をそのまま記載し、未実施の項目を成功として書きません。`Screenshots` には UI 変更がある場合に取得できた範囲を載せます。

## 4. CI の確認

承認された操作の完了後、現在の PR と最新コミットの CI を確認します。

1. `gh pr view --json number,url,headRefOid,state` で PR と head SHA を取得する。
2. `git rev-parse HEAD` と `headRefOid` が一致することを確認する。
3. `gh pr checks <番号> --json name,state,bucket,link,workflow` で状態を確認する。
4. 未完了なら `gh pr checks <番号> --watch --fail-fast --interval 30` を Bash の timeout 600000 ms で実行する。実行は最大 2 回とし、終わらなければ Pending として報告する。
5. 判定に使う実行が head SHA のものかを `gh run list --commit <SHA> --json databaseId,headSha,status,conclusion,name` で確認する。古いコミットの結果は成功に数えない。

CI が成功したら、結果を提示して終了します。常時監視は行いません。

## 5. CI 失敗時

1. `gh run view <run-id> --json jobs` で失敗した Job と Step を特定する。
2. `gh run view <run-id> --log-failed` でログを確認する。必要なら Artifact の取得をユーザーに確認する。
3. 自分の変更が原因か、Runner などの環境問題かを切り分ける。
4. 原因がログで確認できた場合だけローカルで修正し、関連する検証を再実行する。
5. 修正差分と検証結果を提示し、追加の commit と push の承認を得る。
6. 承認後に push し、手順 4 に戻る。

修正と再確認は最大 2 回です。解決しない場合は、調査結果を報告して停止します。

次の方法で CI を通すことはしません。

- CI チェックの無効化やスキップ
- 失敗テストの削除や無効化
- ログを確認しない推測の修正
- 承認のない再 push
- PR のマージ

## 報告

PR URL、head SHA、検証結果、CI の結果（成功 / 失敗 / Pending）、残課題を報告します。
