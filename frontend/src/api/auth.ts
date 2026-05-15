import apiClient from './index'

export const authApi = {
  login: async (formData: FormData) => {
    const response = await apiClient.post('/auth/login', formData, {
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
      },
    })
    return response.data
  },
  register: async (data: any) => {
    const response = await apiClient.post('/auth/register', data)
    return response.data
  },
  getCurrentUser: async () => {
    const response = await apiClient.get('/auth/me')
    return response.data
  },
}
