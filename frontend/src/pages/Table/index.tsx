import {
  ActionType,
  PageContainer,
  type ProColumns,
  ProTable,
} from '@ant-design/pro-components';
import { Button, message, Modal, Form, Input, InputNumber, Switch, Space, Tag } from 'antd';
import React, { useRef, useState } from 'react';
import { DemoProduct, pageProduct, createProduct, updateProduct, deleteProduct } from '@/services/demo';

const TableList: React.FC<unknown> = () => {
  const actionRef = useRef<ActionType>();
  const [modalVisible, setModalVisible] = useState(false);
  const [editingItem, setEditingItem] = useState<DemoProduct.VO | null>(null);
  const [form] = Form.useForm();

  // 创建/更新
  const handleSubmit = async (values: any) => {
    const hide = message.loading(editingItem ? '正在更新...' : '正在创建...');
    try {
      if (editingItem) {
        await updateProduct({ ...values, id: editingItem.id });
        message.success('更新成功');
      } else {
        await createProduct(values);
        message.success('创建成功');
      }
      hide();
      setModalVisible(false);
      setEditingItem(null);
      form.resetFields();
      actionRef.current?.reload();
    } catch (error) {
      hide();
      message.error('操作失败');
    }
  };

  // 删除
  const handleDelete = async (id: string) => {
    Modal.confirm({
      title: '确认删除？',
      content: '删除后数据将无法恢复',
      onOk: async () => {
        const hide = message.loading('正在删除...');
        try {
          await deleteProduct(id);
          hide();
          message.success('删除成功');
          actionRef.current?.reload();
        } catch (error) {
          hide();
          message.error('删除失败');
        }
      },
    });
  };

  const columns: ProColumns<DemoProduct.VO>[] = [
    {
      title: '商品名称',
      dataIndex: 'name',
      key: 'name',
      copyable: true,
      ellipsis: true,
    },
    {
      title: '描述',
      dataIndex: 'description',
      key: 'description',
      ellipsis: true,
      hideInSearch: true,
    },
    {
      title: '价格',
      dataIndex: 'price',
      key: 'price',
      valueType: 'money',
      hideInSearch: true,
    },
    {
      title: '库存',
      dataIndex: 'stock',
      key: 'stock',
      hideInSearch: true,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      valueEnum: {
        DRAFT: { text: '草稿', status: 'Default' },
        PUBLISHED: { text: '已发布', status: 'Success' },
        OFFLINE: { text: '已下架', status: 'Error' },
      },
    },
    {
      title: '激活',
      dataIndex: 'isActive',
      key: 'isActive',
      hideInSearch: true,
      render: (_, record) => (
        <Tag color={record.isActive ? 'green' : 'default'}>
          {record.isActive ? '是' : '否'}
        </Tag>
      ),
    },
    {
      title: '创建时间',
      dataIndex: 'createdAt',
      key: 'createdAt',
      valueType: 'dateTime',
      hideInSearch: true,
    },
    {
      title: '操作',
      valueType: 'option',
      key: 'option',
      render: (_: any, record: DemoProduct.VO) => (
        <Space>
          <a
            onClick={() => {
              setEditingItem(record);
              form.setFieldsValue(record);
              setModalVisible(true);
            }}
          >
            编辑
          </a>
          <a onClick={() => handleDelete(record.id)} style={{ color: 'red' }}>
            删除
          </a>
        </Space>
      ),
    },
  ];

  return (
    <PageContainer header={{ title: '商品管理（CRUD 示例）' }}>
      <ProTable<DemoProduct.VO>
        headerTitle="商品列表"
        actionRef={actionRef}
        rowKey="id"
        search={{ labelWidth: 'auto' }}
        toolBarRender={() => [
          <Button
            key="create"
            type="primary"
            onClick={() => {
              setEditingItem(null);
              form.resetFields();
              setModalVisible(true);
            }}
          >
            新建商品
          </Button>,
        ]}
        request={async (params) => {
          const { current, pageSize, name, status } = params;
          const res = await pageProduct({
            pageNum: current || 1,
            pageSize: pageSize || 10,
            name,
            status,
          });
          return {
            data: res.data?.records || [],
            total: res.data?.total || 0,
            success: res.code === 200,
          };
        }}
        columns={columns}
      />

      <Modal
        title={editingItem ? '编辑商品' : '新建商品'}
        open={modalVisible}
        onCancel={() => {
          setModalVisible(false);
          setEditingItem(null);
          form.resetFields();
        }}
        onOk={() => form.submit()}
      >
        <Form form={form} layout="vertical" onFinish={handleSubmit}>
          <Form.Item name="name" label="商品名称" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea />
          </Form.Item>
          <Form.Item name="price" label="价格" rules={[{ required: true }]}>
            <InputNumber min={0} precision={2} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="stock" label="库存" rules={[{ required: true }]}>
            <InputNumber min={0} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="isActive" label="是否激活" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </PageContainer>
  );
};

export default TableList;
