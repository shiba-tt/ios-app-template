---
name: review-pr
description: Use when the user explicitly runs /review-pr to get an independent read-only code review of a GitHub pull request.
argument-hint: "[PR番号またはPR URL]"
disable-model-invocation: true
context: fork
agent: pr-reviewer
background: false
---

次の Pull Request を、読み取り専用でレビューしてください。

レビュー対象：$ARGUMENTS

- レビュー対象が空の場合は、現在のブランチに紐づく PR を `gh pr view` で特定してください。
- 値は PR 番号またはこのリポジトリの PR URL だけを受け付けます。それ以外の値や、PR を特定できない場合は、別の PR を推測せずにエラーを報告して終了してください。
- 手順と出力形式は、エージェント定義に従ってください。
