import axios from 'axios';
export const api = axios.create({baseURL:'/api',timeout:120000});
export function errorMessage(error:unknown):string {
  if(axios.isAxiosError(error)){const d=error.response?.data?.detail;return typeof d==='string'?d:Array.isArray(d)?d.map((x:{msg:string})=>x.msg).join('; '):error.message;}
  return error instanceof Error?error.message:'Something went wrong. Please try again.';
}
