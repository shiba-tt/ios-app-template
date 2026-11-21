# テスト

- Unit Test は Swift Testing、起動と主要な画面遷移の UI Test は XCUITest を使う。
- 新機能では外から観測できる振る舞いをテストする。外部通信や時刻依存には必要に応じて Fake や Stub を使い、結果を決定的にする。
- UI Test は Accessibility Identifier と要素の出現待ちで同期する。UI を変えたときは Simulator でも目視確認する。
- テストの数値カバレッジ目標は設けない。実行できなかったテストは未検証として報告する。
