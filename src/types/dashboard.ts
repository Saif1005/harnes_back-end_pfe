export interface ProductionPoint {
  period: string;
  quantity_ton: number;
}

export interface ProductionArticleTrend {
  article: string;
  points: ProductionPoint[];
}

export interface ProductionTopArticle {
  article: string;
  quantity_ton: number;
}

export interface ProductionSummary {
  unique_articles: number;
  total_quantity_ton: number;
  active_lines: number;
}

export interface ProductionDashboardResponse {
  start_year: number;
  summary: ProductionSummary;
  article_options: string[];
  monthly_totals: ProductionPoint[];
  top_articles: ProductionTopArticle[];
  article_trends: ProductionArticleTrend[];
}
