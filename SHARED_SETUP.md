# 复检共用位置签报

两版标定都待确认时，复检班只能布置一套触发位置。白班分别封发每版证据，夜班选取实际收到的两版，按同一完整布置核账。现行 V1 单件签报保留。

## 比较组与发件

用一份冻结版开组。比较组固定录制号、两轨各自按原序排列的 `(拍号, 采样序)` 和公开主拍集合。一个组至多六个主拍和十二个副拍。入组冻结版须符合这份身份约定，读数和左右窗宽可不同。组可在源库重开后继续发件，每次开组拥有独立的组身份。公开主拍沿用原录制顺序，也可为空。

发件岗一次发行一份指定冻结版，发件时只需本版原测及固定的组资料。新件只交公开引用、按整条配对或整段汇总的费用，以及组内可核同的匿名标识。令牌对应的隐去位置、提供直接反查的映射或参数留站。隐去主拍的原号、采样序、读数、逐拍候选和逐拍差同样留站。聚合费用、公开配对和组内证据的可核同关系是获准披露结果。已发件及原发行登记固定，收件端沿用另路取得的原发行登记校验实际字节及冻结身份。

## 双件裁决

凭同组两个不同冻结修订的实收号签报。按每个冻结版的含端点采样窗筛选，每主拍分配一个窗内副拍，全程副拍位置严格递增，含所有隐去拍。两件都必须支持完全相同的副拍位置序列。逐版累计全程整数绝对差，对每种共同布置取两版总差的较大值，签出其中最小的值。同值按公开主拍原序下的副拍位置序列取字典序首项，报告把位置写回拍号。没有共同配对时上限和配对均为 `None`，仍可签存。有解且公开主拍为空时配对为 `()`。两轨都空时，空布置费用为零。

报告固定组身份、录制号、请求顺序下的两件实收出处及结果。每个出处含实收号、发件号、冻结修订号和登记中的正文摘要。结果与出处一并签存。坏件及错绑登记拒收，旧件、混组或同修订双选拒签。写入或提交失败无本次新增记录。源站关闭后，隔离库可独立实收、签报和重开按原报告号读取存值。保留 V1 件、单件签报、旧报告及其原调用行为。

## 调用约定

各库沿用 README.md 的初始化入口。下列新增调用使用现有 `RevisionStore`、`ReceiptStore` 和 `ReportStore`。写入使用空闲连接。

| 调用 | 返回 |
| --- | --- |
| `issue.register.open_comparison_group(store, base_revision_id, public_ids)` | 新比较组标识，为非空字符串。 |
| `issue.register.issue_comparison_packet(store, group_id, revision_id)` | `(packet_bytes, registration)`，登记可从 `issue.register.get_issue_registration(connection, issue_id)` 读回。 |
| `intake.receive.receive_packet(receipts, packet_bytes, registration)` | 沿原入口接纳已核准的 V1 或 V2 件并返回实收号。 |
| `review.publish.sign_shared_setup(receipts, reports, first_receipt_id, second_receipt_id)` | 新报告。 |
| `review.retrieve.get_shared_setup_report(reports, report_id)` | 按新报告号读取原报告，未知号返回 `None`。 |

报告提供 `report_id`、`group_id`、`run_id`、`sources`、`upper_cost` 和 `pairs` 属性。`sources` 为按调用顺序排列的二元组，每项提供 `receipt_id`、`issue_id`、`revision_id`、`body_sha256`。`upper_cost` 为整数刻度或 `None`，`pairs` 与原报告一样以两个拍号构成一对。未知组、冻结版或实收号报 `LookupError`，参数、组资格或件校验不符报 `ValueError`。V1 单件由 `sign_review` 签报，报告仍经 `get_report` 领取。

## 夹具与核验

`samples/setup_comparison.json` 的 `single` 和 `double` 是两次独立录制。每项 `revisions` 在该录制的原始主轨上应用本项 `readings` 里的主拍读数替换，并使用本项 `window`。副轨沿用该录制的 `secondary`。按列表顺序导入、冻结，可用前一版作为勘误来源。开组后分别发行需要的版本，再关闭源库。

- `single` 的 `first`、`second`、`third` 供夜班晚选。`first` 加 `second` 签 4，`first` 加 `third` 签 0，两份都给 A→U、B→V，并固定各自的实收出处。`left` 加 `right` 无共同配对。`first` 加 `right` 仍签 4。
- `double` 的 `first` 加 `second` 签 4，公开 A→U、M→T、B→V。两处隐去拍都影响整版总差。
- 从 `samples/tied_run.json` 导入两份内容相同的冻结修订，以原公开拍开组，签 5 并取 A→S2、B→S11。若另开一组使用空公开集合，两版仍签 5，配对为 `()`。
- 用原登记核验改动字节拒收，核验混组、同修订双选及 V1 混选拒签。签报提交被拒后重开，已有报告仍可领取，本次报告未产生。

原运行清单是 `.pointwise-runtime.json`，使用 version 1、kind `cli`，`setup` 是准备命令的参数数组列表，`verify` 和 `demo` 是命令参数数组。交付时让 `verify` 运行原回归和本功能的业务核验，失败退出非零。让 `demo` 展示 `single` 的关源选件结果和隔离库重开领报，原演示仍可单独运行。
