# 0002 — iOS CI 基盤

## Status

Accepted

## Context

テンプレートと、そこから生成した各アプリの変更を GitHub Actions で検証する。リポジトリは Public で、CI は Pull Request のコードを実行する。生成アプリには CI がコピーされる一方、初期化スクリプトとその回帰テストは残らない。

## Decision

- **テスト範囲**：Pull Request は Swift Testing までの高速な検証に留める。XCUITest は実行時間が長く Simulator の状態に影響されやすいため、`main` への push と手動 `full` で実行し、必須チェックにしない。
- **Runner の役割分担**：Xcode を必要としない構文チェック、回帰テスト、actionlint、zizmor は `ubuntu-24.04` で実行する。Swift と Xcode の検証は macOS で実行する。ジョブは依存させず並列に動かす。
- **ジョブ名**：Ubuntu のジョブは `quality-and-security` とする。初期化の検証は生成アプリから外れるため、名前に含めると生成アプリの必須チェック名が実態と合わなくなる。
- **Xcode**：`.xcode-version` を唯一の設定元とし、`/Applications/Xcode_<version>.app` が無い場合や報告されたバージョンが異なる場合は失敗する。2026年11月23日時点で `macos-26` の Xcode は 26.6 までであり、Xcode 27.2 を含む Hosted Runner は preview の `xcode-27` だけである。このため `xcode-27` に固定する。`macos-latest` は使わない。[GitHub Actions runner イメージ](https://github.com/actions/runner-images#available-images)
- **Simulator**：iOS Runtime は `ci.yml` の `IOS_SIMULATOR_RUNTIME` で固定し、識別子の完全一致で選ぶ。機種は候補から選び、無ければ同じ Runtime の別の iPhone を使う。Runtime が無い場合は失敗する。`--family` で将来 iPad を選べる。
- **検証処理**：ローカルと CI で `scripts/check.sh` を共有する。CI はステージごとに呼び出し、実行時間と失敗箇所をステップ単位で確認できるようにする。
- **キャッシュ**：初期段階では導入しない。クリーンな環境で安定して成功することを優先し、実行時間の実績を見てから判断する。
- **セキュリティ**：権限は `contents: read` とし、Secrets と `pull_request_target` を使わない。外部 Action はフルコミット SHA で固定し、Dependabot で更新する。Dependabot には 7 日間の cooldown を設定する。actionlint と zizmor は `mise.toml` で固定し、mise が公式リリースの整合性を検証する。
- **再利用**：アプリ名は `project.yml` から取得し、ワークフローに書かない。各アプリへのコピーで動く構成とし、Reusable Workflows への移行は複数アプリで差分と保守負荷が見えてから判断する。

## Consequences

- UI にのみ現れる不具合は、マージ後の `main` で検出される場合がある。必要な PR では手動 `full` を実行する。
- `xcode-27` は preview のため、キューの待ち時間や内容の変更が起こり得る。GA 後または Xcode の更新時に Runner を見直す。
- actionlint 1.7.12 は `xcode-27` ラベルを知らないため、`.github/actionlint.yaml` に登録している。認識されるようになったら削除する。
- キャッシュがないため、毎回ツールの取得とクリーンビルドを行う。
- Xcode の更新時は `.xcode-version`、`project.yml`、`IOS_SIMULATOR_RUNTIME`、必要に応じて Runner ラベルを揃えて更新する。
