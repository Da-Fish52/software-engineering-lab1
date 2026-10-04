# 软件工程实验一 · 个人编程技能与 Git 操作

- `hello_world.py` —— 编程基本功练习：输出 Hello World
- `hj212_parser.py` —— HJ212-2017 环保协议报文解析类库（AI 辅助生成）
- `test_hj212_parser.py` —— 针对上述类库的断言式自测

## HJ212Parser 提供的四项能力

| 方法 | 职责 |
| --- | --- |
| `is_valid_message` | 报文格式合法性验证（`##` 头、长度字段自洽、CRC 字段为十六进制、必备字段齐全） |
| `validate_crc` | ANSI CRC16 校验（初值 `0xFFFF`，多项式 `0xA001`） |
| `parse_data_segment` | 数据段结构化解析，返回 `键=值` 字典 |
| `extract_monitoring_data` | 从 `CP` 字段提取全部监测因子并结构化封装 |

另有辅助方法 `crc16_ansi`（裸算 CRC）、`split_message`（拆分报文）、`build_message`（按国标拼装报文，供模拟设备上报使用）。

## 报文结构

```
## + 4位长度 + 数据段 + 4位CRC + \r\n
```

- 长度字段 = 数据段字节数 + 4（CRC 占 4 字节），十六进制大写
- CRC16 计算范围：从 `##` 到数据段最后一个字节
- 默认按 GBK 编码还原字节，可通过构造参数切换

## 实现中处理的两个协议陷阱

1. **长度字段不等于数据段长度**：声明值多算了 CRC 的 4 字节，比较时必须减去。
2. **`CP` 字段内部同样用 `;` 分隔子项**，与顶层字段分隔符同形，无法靠 `split` 区分。国标的隐含约定是 `CP` 恒为最后一个字段，所以先切出 `CP=` 之前的部分，剩下的整体作为 `CP` 值；`CP` 内部再用正则匹配整个子项，而不是按分隔符切分。

## 运行

```bash
python hello_world.py
python test_hj212_parser.py
```

## 本次实验的 Git 提交记录

| 提交说明 | 内容 |
| --- | --- |
| `chore: 初始化实验仓库` | 建立目录结构与说明文档 |
| `feat: 实现 Hello World 编程基本功练习` | `hello_world.py` |
| `feat(hj212): 实现 HJ212-2017 报文解析类库` | `hj212_parser.py` |
| `test(hj212): 补充四大能力的断言式自测` | `test_hj212_parser.py` |