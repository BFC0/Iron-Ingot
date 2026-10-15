"""仅对本次维护文档去重，不触及原件与模型。"""
from pathlib import Path
import json
import re

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'output/text_cleanup/20261013T110453410933+0800'
record = json.loads((OUT / 'verification.json').read_text(encoding='utf-8'))
task = ROOT / 'Cesim_任务要求与当前情况说明.md'
content = task.read_text(encoding='utf-8')
# 前后阶段已有专节，交付节只保留协商、生效与发布规则。
for index in (1, 2, 3, 7):
    content = re.sub(rf'^\| {index}\. .*\n', '', content, flags=re.M)
content = content.replace('正式回合按以下生命周期执行：**t回合期初状态与情境 → 模型候选方案 → 个人草稿与预算试算 → 组员协商 → 保存并核对小组决策 → 截止结算与实际结果公布 → 复盘及状态结转 → t+1回合**。', '完整流程为期初核验→模型候选→个人草稿/预算→协商→小组保存→结算→复盘。前三步及复盘按本文对应章节执行，协商和生效边界如下。')
content = content.replace('| 4. 协商小组方案 |', '| 协商小组方案 |').replace('| 5. 保存并核对小组决策 |', '| 保存并核对小组决策 |').replace('| 6. 截止结算与发布 |', '| 截止结算与发布 |')
content = content.replace('本次全项目核验的用户确认：', '此前姓名核验中用户确认：')
task.write_text(re.sub(r'\n{3,}', '\n\n', content), encoding='utf-8', newline='\n')

for name in record['after']:
    path = ROOT / name
    text = path.read_text(encoding='utf-8')
    text = re.sub(r'\n{3,}', '\n\n', text)
    path.write_text(text, encoding='utf-8', newline='\n')

report = ROOT / '建模重审与验收要求.md'
text = report.read_text(encoding='utf-8')
text = text.replace('- 所有预测与财务计算使用Python。数据唯一键包括编号市场、阶段、回合、团队、国家和数据类别；实际需求、销量、玩家预测、预算和模型输出分开保存，缺失不补零。\n- 数量使用千单位、财务金额使用千美元、单位价格使用美元，利率内部使用小数。已知参数关联当期前景来源，经验校准项单独标记。', '- 计算、来源与数据分类沿用[任务说明](Cesim_任务要求与当前情况说明.md)。数量千单位、金额千美元、单位价格美元，利率内部用小数；当期公布参数、经验校准和假设分列。')
report.write_text(text, encoding='utf-8', newline='\n')

overview = ROOT / 'README.md'
text = overview.read_text(encoding='utf-8')
text += '\n本次整理：[工作日志](output/text_cleanup/20261013T110453410933+0800/work_log.md)、[验收记录与改前哈希](output/text_cleanup/20261013T110453410933+0800/verification.json)；编辑前内容完整备份在同目录`before/`。\n'
overview.write_text(text, encoding='utf-8', newline='\n')
assert len(re.findall(r'^\| (协商小组方案|保存并核对小组决策|截止结算与发布) \|', task.read_text(encoding='utf-8'), re.M)) == 3
print('文档去重与换行检查完成')
