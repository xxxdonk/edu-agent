import axios from 'axios';
import {API_BASE_URL, API_ENDPOINTS} from './config';
import type {
  EvaluationResult,
  EvaluationSubmission,
  HealthResponse,
  LearningPath,
  PathGenerateRequest,
  ProfileChatRequest,
  ProfileChatResponse,
  Resource,
  ResourceGenerationRequest,
  StudentProfile,
  TaskAcceptedResponse,
  TaskState,
} from '@/types/api';

const http = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30_000,
  headers: {'Content-Type': 'application/json; charset=utf-8'},
});

export const api = {
  async health(): Promise<HealthResponse> {
    return (await http.get<HealthResponse>(API_ENDPOINTS.health)).data;
  },
  async chat(payload: ProfileChatRequest): Promise<ProfileChatResponse> {
    return (await http.post<ProfileChatResponse>(API_ENDPOINTS.profileChat, payload)).data;
  },
  async profile(studentId: string): Promise<StudentProfile> {
    return (await http.get<StudentProfile>(API_ENDPOINTS.profile(studentId))).data;
  },
  async generatePath(payload: PathGenerateRequest): Promise<LearningPath> {
    return (await http.post<{path: LearningPath}>(API_ENDPOINTS.pathGenerate, payload)).data.path;
  },
  async generateResources(payload: ResourceGenerationRequest): Promise<TaskAcceptedResponse> {
    return (await http.post<TaskAcceptedResponse>(API_ENDPOINTS.resourcesGenerate, payload)).data;
  },
  async task(taskId: string): Promise<TaskState> {
    return (await http.get<TaskState>(API_ENDPOINTS.task(taskId))).data;
  },
  async resource(resourceId: string): Promise<Resource> {
    return (await http.get<Resource>(API_ENDPOINTS.resource(resourceId))).data;
  },
  async evaluate(payload: EvaluationSubmission): Promise<EvaluationResult> {
    return (await http.post<EvaluationResult>(API_ENDPOINTS.evaluation, payload)).data;
  },
};
