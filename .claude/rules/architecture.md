# アーキテクチャ

- Feature-first を採用し、画面、画面固有の型、状態管理を同じ機能ディレクトリに置く。
- 軽量 MVVM を必要に応じて使う。表示だけの View はそのままにし、画面状態や操作が複雑になったら `@Observable` の ViewModel を導入する。
- Composition Root で依存を組み立て、Initializer Injection で渡す。SwiftUI Environment は複数の View 階層で共有が必要な状態に使う。
- Repository は永続化や外部データソースの境界が必要になった時点で導入する。UseCase は複数箇所で再利用する独立した処理などに使う。外部 DI ライブラリは標準採用しない。
- 機能間の参照を抑え、将来必要になったときに Swift Package へ段階的に移せるようにする。
