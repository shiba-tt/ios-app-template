# Swift

- Swift 6 の言語モードを前提とし、非同期処理には Swift Concurrency を使う。
- UI 状態の更新は Main Actor に置き、共有可変状態の所有者と Actor Isolation を明示する。境界を越える型には必要に応じて `Sendable` を使い、コンパイラ診断を解消する。
- Optional は安全に取り扱い、エラーは呼び出し元へ伝えるか、利用者が対処できる形にする。
- SwiftUI の標準 API と具体型から始める。差し替えや再利用が必要になったところで抽象化する。
