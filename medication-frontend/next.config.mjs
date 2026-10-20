/** @type {import('next').NextConfig} */
const nextConfig = {
  // 정적 export: next build -> out/ 정적 산출물 생성 (Cloudflare Pages 등 정적 호스팅 대상)
  output: 'export',

  // 성능 최적화
  experimental: {
    optimizeCss: true, // CSS 최적화
    optimizePackageImports: ['lucide-react'], // 아이콘 라이브러리 최적화
  },

  // 컴파일러 최적화
  compiler: {
    removeConsole: process.env.NODE_ENV === 'production', // 프로덕션에서 console.log 제거
  },

  // 브라우저 OCR — onnxruntime-web 의 기본 진입점은 WebGPU 겸용(JSEP) WASM 28MB 를 요청해
  // Cloudflare Pages 파일 한도(25MiB)를 넘는다. 측정에 쓴 WASM 전용 빌드(14MB)로 고정한다.
  // ppu-paddle-ocr 내부의 import 도 같은 별칭을 타므로 엔진 인스턴스가 하나로 유지된다.
  // 런타임 파일이 복사본과 맞는지는 build:pages 끝의 fetch-ocr-assets --verify-build 가 대조한다.
  turbopack: {
    resolveAlias: {
      'onnxruntime-web': 'onnxruntime-web/wasm',
    },
  },

  images: {
    // 정적 export 에는 이미지 최적화 서버가 없으므로 최적화 비활성화 (원본 그대로 서빙)
    unoptimized: true,
    // 외부 이미지 도메인 허용 (필요시 추가)
    remotePatterns: [],
  },

  // 정적 export 는 rewrites(서버 프록시)를 지원하지 않는다.
  // API 호출은 axios baseURL(config.API_BASE_URL = NEXT_PUBLIC_API_BASE_URL)로 백엔드를 직접 호출한다.
}

export default nextConfig
