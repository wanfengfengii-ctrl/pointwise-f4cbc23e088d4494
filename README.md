# 双轨振动录制档案

材料试验中心用两台记录仪采集振动试验。白班资料员冻结双轨并制作固定交班件。夜班在源库关闭后使用实收件和补给锚票核账，凭总差和公开配对判断是否补检。晨班按报告号领取原结论。

## 运行

使用 Python 3.11 标准库。在项目根目录运行：

```sh
python3 -B check_project.py
python3 -B demo.py
```

`check_project.py` 是交付环境提供的完整回归入口。也可直接运行 `python3 -B -m unittest discover -s tests -t .`。演示从 `samples/` 加载有限数据，在独立临时源库和隔离库完成导入、冻结、预览、发行、关源、实收、签报与重开领取。两个单锚各为 0 刻度，合查为 5 刻度，移除唯一中间续接拍后合查为无解。并列样例计入隐去首尾的 2 和 3 刻度，在双项同差时按副轨原序取 `S2`。

## 一天的交班

1. 实验员将两轨原拍按记录仪采样顺序交回，导入产生草稿号。
2. 资料员可引用原修订追加勘误，并冻结选定草稿，后续按冻结号引用。
3. 资料员在线查看最低差和全拍见证，据此核对原始记录。
4. 发件岗选择可公开主拍，固定正文并取得原发行登记和发件号。
5. 源站关库。夜班把所收字节和随件原登记交隔离库校验，取得实收号。
6. 夜班在指定实收号上提交零至两张公开配对锚票。
7. 复核端签出精确最小总差和全部公开配对，或签存无解，供补检判断。
8. 晨班重开隔离库，按报告号领取原结论和实收出处。

## 计量和披露

每拍由 `(拍号, 采样序, 读数)` 表示。拍号是非空字符串，在本轨唯一。采样序和读数为整数，布尔值不作整数使用。采样序严格递增，允许间隔和负值。默认候选窗为 `[主拍采样序 - 2, 主拍采样序 + 2]`，可随草稿指定左右非负整数窗宽。候选资格采用共同采样单位，含两端。每个主拍必须选一个窗内副拍，副轨位置全程严格递增。每拍的成本是读数绝对差，整次以整数刻度相加。原轨序列和成本在冻结后固定。无应计拍时空路径成本为 0。

在线预览在同差时取全部副拍位置的字典序首项。离线在同差时只比较公开主拍原序下的副拍位置序列，报告以原拍号表示配对。空披露时，全程仍参与占位和计差，有解时公开配对为空元组。无解时总差和配对均为 `None`。

V1 外层包含 `version`、`issue_id`、`sha256` 和 Base64 编码的 `body`。实收以外部随件保管的原发行登记作为信任来源，核对发件号、正文字节摘要和正文冻结身份。正文带 `run_id`、`revision_id`、`main`、`secondary` 和 `evidence`。两个有序目录分别列公开主拍和可引用副拍号。未披露主拍的逐拍身份、采样、读数、逐拍候选及在线见证留在源站。派生证据的端点引用目录中从零起算的位置。相邻公开端点之间的记录包含严格接续的最小段差，计入目的拍。带空端点的记录表示从开头进入、从末个公开拍走到结尾，或无公开拍时覆盖全程。缺少记录表示该段没有可行接续。

## Python 接口

源端从 `recording.revision_store` 构造 `RevisionStore(connection)` 并调用 `initialize()`，再以 `issue.register.initialize_issue_store(connection)` 初始化发行登记。隔离端从 `intake.receipts` 和 `review.report_store` 构造 `ReceiptStore(connection)` 和 `ReportStore(connection)`，分别调用 `initialize()`。各端使用独立 SQLite 文件。初始化只建缺失表，可随重开重复执行，已有记录保留。写入入口拥有单次事务，使用空闲连接调用。调用方关闭连接并保管原发行登记。修订号、发件号、实收号和报告号分别在对应归档库内解释。

| 入口 | 输入与返回 |
| --- | --- |
| `recording.import_run.import_run` | `(store, run_id, main, secondary, *, corrects=None, window=(2, 2))` 返回草稿修订号。若填勘误来源，须指向同一录制的现有修订。 |
| `recording.revisions.freeze_run` | `(store, revision_id)` 冻结指定合格修订并返回同一号码。重复冻结同一修订保持号码。 |
| `alignment.reference.preview` | `(store, revision_id, anchors=())` 接受冻结版原拍锚，返回 `AlignmentWitness` 或 `None`。见证包括 `provenance`、`total_cost` 和带两轨原拍的 `pairs`。 |
| `issue.register.issue_packet` | `(store, revision_id, public_ids)` 返回 `(packet_bytes, IssueRegistration)`。`get_issue_registration(connection, issue_id)` 可读取原登记。 |
| `intake.receive.receive_packet` | `(receipts, packet_bytes, registration)` 实收并返回实收号。`ReceiptStore.get_receipt(receipt_id)` 读取并重验该固定件。 |
| `review.publish.sign_review` | `(receipts, reports, receipt_id, anchors=())` 接受至多两个 `(公开主拍号, 副拍号)`，签存并返回 `SignedReport`。合法无解也签存。 |
| `review.retrieve.get_report` | `(reports, report_id)` 返回存下的 `SignedReport`，未知合法号码返回 `None`。 |

输错原拍、错序、重复身份、非法公开范围、勘误来源不符、混件和非法锚以 `ValueError` 拒绝。未知冻结修订或实收号用于业务操作时抛出 `LookupError`。数据库错误由 SQLite 异常表示，事务失败没有新成果。两张不同的公开主拍同时锚到同一副拍属于合法的无解查询。签报存下实收号、发件身份、摘要、归一锚、总差和公开配对。后续重发或重开库不改变既有签报。
