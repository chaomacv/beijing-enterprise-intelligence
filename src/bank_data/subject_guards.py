"""Conservative organization-name guard shared by mapping and model extraction."""
import re

ORG_MARKERS=('公司','企业','合作社','事务所','研究院','研究所','中心','医院','学校','学院','大学','商店','商行','工厂','厂','工作室','经营部','服务部','书店','饭店','餐厅','宾馆','酒店','局','委员会','协会','基金会','银行','支行','法院','检察院','管理处','服务站','超市','诊所','卫生院','药店','药房','俱乐部','集团','农场','养殖场','门市部','理发店','美容院')
GENERIC_ORGANIZATIONS={'企业','公司','单位','机构','供应商','投标人','采购人','代理机构','中小企业','小微企业','大型企业','中型企业','小型企业','微型企业','国有企业','民营企业','外资企业','事业单位','行政机关','政府部门','残疾人福利性单位','监狱企业','联合体','建设单位','施工单位','审查机构','有限公司','有限责任公司','股份有限公司','company','corporation','llc','ltd','limited','hospital','school'}
DOCUMENT_NAME_SUFFIXES=('声明函','承诺书','资格要求','资格条件','报名条件','合同条款','招标文件','采购文件','投标文件','企业认定','行政处罚','监督检查结果','名单','名录','名册','清单','扩建项目')


def recognizable_organization(value):
    markers=ORG_MARKERS+('政府','居委会','中学','小学','幼儿园','办事处','办公室')
    if value.strip().casefold() in GENERIC_ORGANIZATIONS or value.strip() in markers or value.strip().endswith(DOCUMENT_NAME_SUFFIXES):return False
    return len(value)<=200 and (any(marker in value for marker in markers) or
        bool(re.search(r'\b(?:ltd|limited|inc|llc|corporation|llp|university|school|hospital)\b',value,re.IGNORECASE)))
