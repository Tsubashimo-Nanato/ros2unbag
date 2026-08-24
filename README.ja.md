# ROSBagel

[English](README.md) | 日本語 | [简体中文](README.zh-CN.md)

[![Release](https://img.shields.io/badge/release-v1.6.2-f59e0b)](https://github.com/Tsubashimo-Nanato/ROSBagel/releases)
![Python](https://img.shields.io/badge/python-3.10--3.13-3776ab)
[![License](https://img.shields.io/badge/license-AGPL--3.0--or--later-4c1)](LICENSE)
![GUI](https://img.shields.io/badge/GUI-active_development-ef4444)

ROSBagelは、Windows上でROS 1/2のbagをオフラインかつ読み取り専用で確認・エクスポートするためのツールです。ROS環境を一式インストールせずに、CLI、対話型シェル、PySide6製のタイムラインビューアを利用できます。

機能、対応形式、コマンドに関する最新かつ完全な説明は、[英語版README](README.md)を基準とします。

![ROSBagel Timeline Viewer](docs/media/gui-timeline.png)

> [!NOTE]
> CLIとエクスポーターは現在利用できます。GUIは開発中のため、操作方法や描画動作がリリース間で変わる場合があります。

## 主な機能

| 領域 | 内容 |
| --- | --- |
| 確認 | topicツリー、詳細スキャン、メッセージ数、収録時間、タイムスタンプ、近傍メッセージの検索 |
| エクスポート | CSV、Parquet、SQLite、JSONL、NPZ、raw CDR、PNG/JPG、MP4、PCD、PLY |
| 対話操作 | 履歴、topic補完、選択エクスポートキューを備えた対話型シェル |
| 可視化 | タイムライン操作、画像再生、分割表示、レーンラインのオーバーレイ、点群プレビュー、ライト／ダークテーマ |
| オフライン利用 | `rosbags`によるrosbag1／rosbag2の読み取りと、raw ROS 2データ向けSQLiteフォールバック |

bagファイル自体は書き換えません。GUI設定はsidecar JSONに保存でき、無損失エクスポートは専用のエクスポーターパスで処理されます。

## クイックスタート

```powershell
git clone https://github.com/Tsubashimo-Nanato/ROSBagel.git
cd ROSBagel
py -m pip install -e .[gui]

bagel topics .\my_bag
bagel gui .\my_bag
```

Windows向けの補助スクリプトも利用できます。

```bat
install.bat
install.bat gui
```

`install.bat`の実行直後に`bagel`コマンドが見つからない場合は、ターミナルを再起動してください。

対話型シェルは次のコマンドで開始します。

```powershell
bagel
```

代表的な直接実行コマンドは以下のとおりです。

```powershell
bagel scan .\my_bag --out .\scan
bagel export .\my_bag --topic /imu --format parquet --out .\export
bagel export .\my_bag --topic /camera/image_raw --format png --out .\export
bagel export .\my_bag --topic /points --format ply --out .\export
bagel export-all .\my_bag --out .\export
```

## 実データによる確認

以下の2×2画像は、ローカルの検証用bagに含まれる同一時刻のRGBカメラ、認識結果、二値マスク、3本のレーンライン`PointCloud2` topicから生成したものです。

![検証用bagの同期4分割表示](docs/media/validation-run-2x2.png)

![認識結果と二値マスクのアニメーション](docs/media/validation-run.gif)

[MP4プレビューを開く](docs/media/validation-run.mp4)

これらは記録済みフレームから、英語版READMEに記載したエクスポート手順で生成しています。検証用bagそのものは本リポジトリでは配布していません。

## 現在の制約

- GUIはライブROS subscriber、recorder、node graph inspector、またはRViz2の完全な代替ではありません。
- 画像デコードは一般的なRGB/BGR/RGBA/BGRA、mono8/16、`16UC1`、`32FC1`に対応しています。
- MP4 codecの利用可否はOpenCVのビルドと実行環境に依存します。
- SQLiteフォールバックではCDRメッセージをデシリアライズできません。デコードを伴うエクスポートには`rosbags`バックエンドを使用してください。
- カスタムメッセージの対応範囲は、bagメタデータから`rosbags`が取得できる型定義に依存します。
- オプションの3D点群レンダラーには、VisPy／OpenGLが動作する環境が必要です。それ以外の機能は、このレンダラーが利用できない場合でも使用できます。
- bagには非公開のカメラ、センサー、地図、研究データが含まれる場合があります。出力内容は公開前に必ず確認してください。

## コントリビューション

再現手順の明確な不具合報告、境界条件に関する情報、小規模なpull requestを歓迎します。詳細は[CONTRIBUTING.md](CONTRIBUTING.md)を参照してください。確認と匿名化が完了していない非公開bagをpublic issueに添付しないでください。

## ライセンス

ROSBagelは`AGPL-3.0-or-later`で提供されています。詳細は[LICENSE](LICENSE)を参照してください。
