# -*- coding: utf-8 -*-
"""HJ212Parser —— HJ212-2017 污染物在线监控系统数据传输标准 报文解析类库

四大核心能力：
    1. is_valid_message        报文格式合法性验证
    2. validate_crc            基于 ANSI 标准的 CRC16 校验
    3. parse_data_segment      数据段结构化解析
    4. extract_monitoring_data CP 字段中监测因子的精准提取与封装

报文整体结构：
    ## + 4位长度 + 数据段 + 4位CRC + \r\n

示例：
    ##00CBST=32;CN=2011;PW=123456;MN=8888888000001;Flag=5;
    CP=&&DataTime=20260914103000;a34004,Rtd=1.234,Flag=5;a34005,Rtd=56.78,Flag=5&&1A68

长度字段 = 数据段字节数 + 4（CRC 占 4 字节），以十六进制大写表示。
CRC16 计算范围：从 "##" 开始到数据段最后一个字节。
"""

import re

_HEX_PATTERN = re.compile(r'^[0-9A-Fa-f]+$')

# CP 内部子项以 ';' 分隔（部分厂商用 ','），但 ',' 同时也是因子属性的分隔符
# （如 a34004,Rtd=1.234,Flag=5），所以不能按分隔符切字符串。
# 改为直接"匹配"一个完整子项：因子编码 + 其后逗号连接的属性串。
_CP_ITEM_PATTERN = re.compile(
    r'DataTime=([^;&,]+)'      # 分组1：采样时间
    r'|[A-Za-z]{1,3}\d{2,6}'   # 因子编码，如 a34004
    r'(?:,[^;&]*)*'            # 该因子后跟的逗号属性
)

HEADER_FLAG = '##'
LEN_WIDTH = 4
CRC_WIDTH = 4
_FIELD_SEP = ';'

REQUIRED_KEYS = frozenset(('ST', 'MN', 'CP'))


class HJ212Parser(object):
    """HJ212-2017 报文解析器。

    默认按 GBK 编码还原字节（国标正文编码），可按现场实际传参。
    """

    POLYNOMIAL = 0xA001      # ANSI CRC16 反转多项式
    INITIAL_VALUE = 0xFFFF

    def __init__(self, encoding='gbk'):
        self.encoding = encoding
        self._crc_table = self._build_crc_table()

    # ------------------------------------------------------------------ #
    # 内部工具
    # ------------------------------------------------------------------ #
    def _build_crc_table(self):
        """预计算 0~255 的 CRC 查表结果，把每个字节的运算从 8 次压到 1 次。"""
        table = []
        for index in range(256):
            crc = index
            for _ in range(8):
                if crc & 1:
                    crc = (crc >> 1) ^ self.POLYNOMIAL
                else:
                    crc >>= 1
            table.append(crc)
        return table

    def crc16_ansi(self, data):
        """标准 ANSI CRC16：初值 0xFFFF，多项式 0xA001（0x8005 的反射形式）。"""
        crc = self.INITIAL_VALUE
        for byte in bytearray(data):
            crc = (crc >> 8) ^ self._crc_table[(crc ^ byte) & 0xFF]
        return crc

    @staticmethod
    def _is_hex(text):
        return bool(text) and _HEX_PATTERN.match(text) is not None

    @staticmethod
    def _to_number(text):
        """监测值可能是 '1.23'，也可能是 '***'（缺测）或 '-9999'（无效）。"""
        try:
            return float(text)
        except (TypeError, ValueError):
            return text

    def split_message(self, message):
        """把报文机械地拆成三段，不做合法性判断。

        返回 (校验覆盖区, 数据段, CRC 十六进制串)。
        """
        body = message.strip()
        data_start = len(HEADER_FLAG) + LEN_WIDTH
        data_end = len(body) - CRC_WIDTH
        return body[:data_end], body[data_start:data_end], body[data_end:].upper()

    # ------------------------------------------------------------------ #
    # 能力一：报文格式合法性验证
    # ------------------------------------------------------------------ #
    def is_valid_message(self, message):
        """逐项检查报文是否满足 ##+长度+数据段+CRC+\\r\\n 的结构约束。"""
        if not isinstance(message, str):
            return False

        body = message.strip()
        min_length = len(HEADER_FLAG) + LEN_WIDTH + CRC_WIDTH
        if not body.startswith(HEADER_FLAG) or len(body) < min_length:
            return False

        length_field = body[len(HEADER_FLAG):len(HEADER_FLAG) + LEN_WIDTH]
        crc_field = body[-CRC_WIDTH:]
        if len(length_field) != LEN_WIDTH or not self._is_hex(length_field):
            return False
        if not self._is_hex(crc_field):
            return False

        # 长度字段必须自洽：声明长度 = 实际数据段长度 + CRC 的 4 字节
        declared = int(length_field, 16)
        actual = len(body) - len(HEADER_FLAG) - LEN_WIDTH - CRC_WIDTH
        if declared - CRC_WIDTH != actual:
            return False

        # 数据段至少要含系统编码、监测点编码、数据段标识
        data_segment = body[len(HEADER_FLAG) + LEN_WIDTH:-CRC_WIDTH]
        keys = {item.split('=', 1)[0].strip()
                for item in data_segment.split(';') if '=' in item}
        return REQUIRED_KEYS.issubset(keys)

    # ------------------------------------------------------------------ #
    # 能力二：CRC16 校验
    # ------------------------------------------------------------------ #
    def validate_crc(self, message):
        """重算报文 CRC，与报文携带的 CRC 比对（大小写不敏感）。"""
        if not self.is_valid_message(message):
            return False
        covered, _, crc_field = self.split_message(message)
        expected = '%04X' % self.crc16_ansi(covered.encode(self.encoding))
        return expected == crc_field

    # ------------------------------------------------------------------ #
    # 能力三：数据段结构化解析
    # ------------------------------------------------------------------ #
    def parse_data_segment(self, message):
        """把 'ST=32;CN=2011;...;CP=&&...&&' 拆成字典。

        注意：CP 内部同样使用 ';' 分隔子项，与顶层字段分隔符同形，
        无法靠 split 区分。国标的解法是 CP 恒为最后一个字段，
        因此这里先把 CP= 之前的内容按 ';' 切分，剩下的整体作为 CP 值。
        """
        if not self.is_valid_message(message):
            raise ValueError('报文格式非法，拒绝解析数据段')

        _, data_segment, _ = self.split_message(message)
        fields = {}

        cp_start = data_segment.find('CP=')
        if cp_start < 0:
            head, cp_value = data_segment, ''
        else:
            head = data_segment[:cp_start].rstrip(_FIELD_SEP)
            cp_value = data_segment[cp_start + len('CP='):]

        for item in head.split(_FIELD_SEP):
            if not item or '=' not in item:
                continue
            key, value = item.split('=', 1)
            fields[key.strip()] = value.strip()

        if cp_value:
            fields['CP'] = cp_value.strip()
        return fields

    # ------------------------------------------------------------------ #
    # 能力四：监测因子提取与封装
    # ------------------------------------------------------------------ #
    def extract_monitoring_data(self, message):
        """从 CP 字段提取全部监测因子，返回封装好的结构。

        CP 结构： &&DataTime=20260914103000;因子1属性;因子2属性&&
        子项以 ';'（部分厂商用 ','）分隔，每个因子形如
        'a34004,Rtd=1.234,Flag=5'，Rtd 为实时值。
        """
        fields = self.parse_data_segment(message)
        cp = fields.get('CP', '').strip()
        if cp.startswith('&&'):
            cp = cp[2:]
        if cp.endswith('&&'):
            cp = cp[:-2]

        data_time = None
        items = {}

        for match in _CP_ITEM_PATTERN.finditer(cp):
            # 分组1命中即 DataTime=xxx
            if match.group(1) is not None:
                data_time = match.group(1).strip()
                continue

            text = match.group(0).strip().strip(_FIELD_SEP).strip()
            parts = text.split(',')
            head = parts[0].strip()

            attributes = {}
            for part in parts[1:]:
                if '=' not in part:
                    continue
                attr_name, attr_value = part.split('=', 1)
                attributes[attr_name.strip()] = attr_value.strip()

            if 'Rtd' not in attributes:
                continue

            items[head] = {
                'factor': head,
                'value': self._to_number(attributes['Rtd']),
                'flag': attributes.get('Flag'),
                'avg': self._to_number(attributes['Avg']) if 'Avg' in attributes else None,
                'max': self._to_number(attributes['Max']) if 'Max' in attributes else None,
                'min': self._to_number(attributes['Min']) if 'Min' in attributes else None,
                'raw': text,
            }

        return {
            'system_code': fields.get('ST'),
            'point_code': fields.get('MN'),
            'password': fields.get('PW'),
            'data_time': data_time,
            'factor_count': len(items),
            'items': items,
        }

    # ------------------------------------------------------------------ #
    # 辅助：按国标拼装报文（自测、模拟设备上报时使用）
    # ------------------------------------------------------------------ #
    def build_message(self, data_segment):
        """给定数据段，自动补齐长度字段与 CRC，返回完整报文。"""
        length = '%04X' % (len(data_segment) + CRC_WIDTH)
        body = HEADER_FLAG + length + data_segment
        crc = '%04X' % self.crc16_ansi(body.encode(self.encoding))
        return body + crc + '\r\n'