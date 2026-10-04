# -*- coding: utf-8 -*-
"""HJ212Parser 自测：构造合法报文验证四大能力，再注入错误验证拦截能力。"""

from hj212_parser import HJ212Parser

DATA_SEGMENT = (
    'ST=32;CN=2011;PW=123456;MN=8888888000001;Flag=5;'
    'CP=&&DataTime=20260914103000;'
    'a34004,Rtd=1.234,Flag=5;'
    'a34005,Rtd=56.78,Flag=5;'
    'a01001,Rtd=0.021,Avg=0.02,Max=0.03,Min=0.01,Flag=1;'
    'a19001,Rtd=***,Flag=5&&'
)


def check(title, actual, expected):
    flag = 'PASS' if actual == expected else 'FAIL'
    print('[%s] %-24s 实际=%r 期望=%r' % (flag, title, actual, expected))
    assert actual == expected, '%s 不符合预期' % title


def main():
    parser = HJ212Parser()
    message = parser.build_message(DATA_SEGMENT)

    print('报文:', repr(message))
    print('-' * 60)

    # 能力一：格式合法性
    check('格式合法性', parser.is_valid_message(message), True)
    # 能力二：CRC16
    check('CRC 校验', parser.validate_crc(message), True)
    # 能力三：数据段结构化
    fields = parser.parse_data_segment(message)
    check('字段 ST', fields.get('ST'), '32')
    check('字段 MN', fields.get('MN'), '8888888000001')
    check('字段数量', len(fields), 6)
    # 能力四：监测因子提取与封装
    result = parser.extract_monitoring_data(message)
    check('数据时间', result['data_time'], '20260914103000')
    check('因子数量', result['factor_count'], 4)
    check('因子 a34004', result['items']['a34004']['value'], 1.234)
    check('因子 a34005', result['items']['a34005']['value'], 56.78)
    check('因子 a01001 平均值', result['items']['a01001']['avg'], 0.02)
    check('缺测值原样保留', result['items']['a19001']['value'], '***')

    print('-' * 60)
    print('反向验证（下面必须全部拦截）')
    check('篡改数据后 CRC', parser.validate_crc(message.replace('1.234', '9.999')), False)
    check('缺少 ## 头', parser.is_valid_message(message.lstrip('#')), False)
    check('长度字段错误', parser.is_valid_message('##0000' + DATA_SEGMENT + '0000'), False)
    check('CRC 非十六进制', parser.is_valid_message(message[:-4] + 'ZZZZ'), False)
    check('数据段缺 CP', parser.is_valid_message(parser.build_message('ST=32;CN=2011')), False)

    print('-' * 60)
    print('全部断言通过')


if __name__ == '__main__':
    main()