export interface DemoCase {
  id: 'visual_beginner' | 'exam_oriented' | 'project_practice';
  code: 'A' | 'B' | 'C';
  name: string;
  summary: string;
  input: string;
}

// Mirrors the non-sensitive input text in scripts/demo_cases.json. Keeping this
// small browser-side copy avoids exposing local paths or coupling Vite to files
// outside the frontend root.
export const demoCases: DemoCase[] = [
  {
    id: 'visual_beginner',
    code: 'A',
    name: '初学视觉型',
    summary: '零基础 · 图示与类比 · 每天 45 分钟',
    input: '我是计算机科学专业大一学生，刚开始学习机器学习，线性代数基础和梯度下降都很薄弱，希望看懂基础分类模型。每天可以学习45分钟，偏好图示、思维导图和生活类比。',
  },
  {
    id: 'exam_oriented',
    code: 'B',
    name: '考试型',
    summary: '期末复习 · 分层练习 · 每天 60 分钟',
    input: '我是数据科学专业大三学生，正在复习机器学习期末考试，已经学过回归和分类，但模型评估、过拟合和正则化容易混淆。目标是考试达到85分，每天可以学习60分钟，偏好分层练习、公式总结和错题解析。',
  },
  {
    id: 'project_practice',
    code: 'C',
    name: '项目实践型',
    summary: '分类项目 · 代码实验 · 每天 90 分钟',
    input: '我是人工智能专业大二学生，目前课程是机器学习，已有Python和机器学习基础，正在做一个客户流失分类项目，对逻辑回归、模型选择和参数调优不熟。希望完成可运行项目并比较模型效果，每天可以学习90分钟，偏好代码案例、实验和项目任务。',
  },
];
