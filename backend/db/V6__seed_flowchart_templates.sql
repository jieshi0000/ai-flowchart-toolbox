-- Day 2: 系统内置模板。config 保存可直接作为 DiagramDocument 输入的权威结构。
INSERT INTO flowchart_template (
    id, user_id, type, category, name, description, config, sort_order, enabled
)
VALUES
(
    '01900000-0000-7000-8000-000000000101', NULL, 'diagram_generate', '审批', '请假审批',
    '员工提交请假申请，主管审批；不通过时退回修改。',
    '{
      "title": "请假审批流程",
      "direction": "TB",
      "nodes": [
        {"id":"start","type":"start","label":"员工提交请假申请","position":{"x":0,"y":0}},
        {"id":"review","type":"decision","label":"主管是否批准","position":{"x":0,"y":140}},
        {"id":"notify","type":"process","label":"通知员工审批结果","position":{"x":-160,"y":280}},
        {"id":"revise","type":"process","label":"退回修改申请","position":{"x":160,"y":280}},
        {"id":"end","type":"end","label":"流程结束","position":{"x":0,"y":420}}
      ],
      "edges": [
        {"id":"e-start-review","source":"start","target":"review"},
        {"id":"e-review-notify","source":"review","target":"notify","label":"是"},
        {"id":"e-review-revise","source":"review","target":"revise","label":"否"},
        {"id":"e-revise-review","source":"revise","target":"review","label":"重新提交"},
        {"id":"e-notify-end","source":"notify","target":"end"}
      ],
      "metadata":{"version":1}
    }'::jsonb,
    10, TRUE
),
(
    '01900000-0000-7000-8000-000000000102', NULL, 'diagram_generate', '用户', '用户注册',
    '用户填写注册信息，系统校验后创建账号并发送欢迎通知。',
    '{
      "title": "用户注册流程",
      "direction": "LR",
      "nodes": [
        {"id":"start","type":"start","label":"开始注册","position":{"x":0,"y":0}},
        {"id":"form","type":"input_output","label":"填写注册信息","position":{"x":180,"y":0}},
        {"id":"validate","type":"decision","label":"信息是否有效","position":{"x":380,"y":0}},
        {"id":"create","type":"process","label":"创建用户账号","position":{"x":580,"y":-100}},
        {"id":"welcome","type":"subprocess","label":"发送欢迎通知","position":{"x":780,"y":-100}},
        {"id":"end","type":"end","label":"注册完成","position":{"x":980,"y":-100}},
        {"id":"fix","type":"process","label":"提示修改信息","position":{"x":580,"y":120}}
      ],
      "edges": [
        {"id":"e1","source":"start","target":"form"},
        {"id":"e2","source":"form","target":"validate"},
        {"id":"e3","source":"validate","target":"create","label":"是"},
        {"id":"e4","source":"validate","target":"fix","label":"否"},
        {"id":"e5","source":"fix","target":"form"},
        {"id":"e6","source":"create","target":"welcome"},
        {"id":"e7","source":"welcome","target":"end"}
      ],
      "metadata":{"version":1}
    }'::jsonb,
    20, TRUE
),
(
    '01900000-0000-7000-8000-000000000103', NULL, 'diagram_generate', '订单', '订单处理',
    '接收订单，校验库存，完成支付并安排发货。',
    '{
      "title": "订单处理流程",
      "direction": "TB",
      "nodes": [
        {"id":"start","type":"start","label":"收到订单","position":{"x":0,"y":0}},
        {"id":"stock","type":"decision","label":"库存是否充足","position":{"x":0,"y":140}},
        {"id":"pay","type":"process","label":"完成订单支付","position":{"x":-160,"y":280}},
        {"id":"ship","type":"subprocess","label":"安排发货","position":{"x":-160,"y":420}},
        {"id":"done","type":"end","label":"订单完成","position":{"x":-160,"y":560}},
        {"id":"out","type":"input_output","label":"通知缺货","position":{"x":180,"y":280}},
        {"id":"cancel","type":"end","label":"订单取消","position":{"x":180,"y":420}}
      ],
      "edges": [
        {"id":"e1","source":"start","target":"stock"},
        {"id":"e2","source":"stock","target":"pay","label":"是"},
        {"id":"e3","source":"stock","target":"out","label":"否"},
        {"id":"e4","source":"pay","target":"ship"},
        {"id":"e5","source":"ship","target":"done"},
        {"id":"e6","source":"out","target":"cancel"}
      ],
      "metadata":{"version":1}
    }'::jsonb,
    30, TRUE
),
(
    '01900000-0000-7000-8000-000000000104', NULL, 'diagram_generate', '接口', '登录校验',
    '用户提交账号密码，系统校验身份并决定是否进入系统。',
    '{
      "title": "登录校验流程",
      "direction": "LR",
      "nodes": [
        {"id":"start","type":"start","label":"打开登录页","position":{"x":0,"y":0}},
        {"id":"credentials","type":"input_output","label":"输入账号和密码","position":{"x":180,"y":0}},
        {"id":"auth","type":"decision","label":"凭据是否正确","position":{"x":400,"y":0}},
        {"id":"home","type":"process","label":"进入系统首页","position":{"x":620,"y":-100}},
        {"id":"success","type":"end","label":"登录成功","position":{"x":840,"y":-100}},
        {"id":"error","type":"process","label":"显示错误提示","position":{"x":620,"y":120}}
      ],
      "edges": [
        {"id":"e1","source":"start","target":"credentials"},
        {"id":"e2","source":"credentials","target":"auth"},
        {"id":"e3","source":"auth","target":"home","label":"是"},
        {"id":"e4","source":"auth","target":"error","label":"否"},
        {"id":"e5","source":"error","target":"credentials","label":"重试"},
        {"id":"e6","source":"home","target":"success"}
      ],
      "metadata":{"version":1}
    }'::jsonb,
    40, TRUE
)
ON CONFLICT (id) DO NOTHING;
