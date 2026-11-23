---
name: implement-feature
description: Use when the user asks to add, change, or fix an iOS app feature, screen, or behavior in this SwiftUI project (例：「設定画面を追加して」「このバグを直して」「この画面を改善して」).
argument-hint: "[実装したい機能や修正内容]"
---

# implement-feature

依頼内容：$ARGUMENTS

依頼内容が空の場合は、会話中のユーザーの要望を対象にします。

この Skill の成果物は、実装、外部から観測できる振る舞いのテスト、検証結果の報告です。commit、push、PR 作成はこの Skill では行いません。

## 手順

1. 要望と受け入れ条件を整理する。曖昧さが実装結果を変える場合だけ質問する。
2. `CLAUDE.md` と `.claude/rules/` を確認し、既存の Feature、View、ViewModel、テストを調査する。
3. 下の基準で影響範囲とリスクを判定する。
4. 事前承認が必要な変更は、実装前に承認を得る。
5. 既存の規約に沿って SwiftUI 機能を実装する。
6. 変更した振る舞いのテストを追加する。Unit Test は Swift Testing、起動と主要な画面遷移は XCUITest を使う。
7. 実装が一区切りついたら `verify-ios` で検証する。通常は `quick`、UI の変更で重点確認が必要なら `full` を使う。
8. 下の形式で報告する。

## リスク判定

変更の行数ではなく、影響範囲と取り消しにくさで判定します。ユーザーが同じ設計をすでに明確に承認している場合は、再度承認を求めません。

| 判定 | 対象 | 進め方 |
| --- | --- | --- |
| 自律実装 | 小さな SwiftUI 画面の追加、既存機能のバグ修正、ViewModel の軽微な修正、Unit Test の追加、Accessibility Identifier の追加、UI の小規模な改善 | そのまま実装する |
| 事前承認 | 外部ライブラリの導入、永続化方式の新規導入・変更、DI 方式の変更、アーキテクチャやレイヤー構成の大幅変更、アプリ全体の状態管理の再設計、認証・課金・個人情報の扱い、既存の公開インターフェースへの破壊的変更、大量のファイル削除や移動 | 方針、影響範囲、代替案を提示し、承認後に実装する |

## 報告

- 変更内容と主な設計判断
- 追加・更新したテスト
- `verify-ios` の結果表
- 残課題と、未検証の項目
