from django.contrib import admin
from django.urls import path, include, re_path
from rest_framework.routers import DefaultRouter

from integration_core.views import ExperimentDeleteView, CompressSimulationView, ExperimentListView, ExperimentParentCheckView, VideoHLSView, ExperimentCreateView, ExperimentDetailView, ExperimentStartView, ExperimentStatusView,ExperimentStopView,TemplateExperimentView # 引入 ExperimentListView 视图集

urlpatterns = [    
    path('experimentList/', ExperimentListView.as_view(),  name='experiment_list'),
    path('hlsVideo/',VideoHLSView.as_view(), name='hlsVideo'),
    path('experimentCreate/',ExperimentCreateView.as_view(),name='experiment_create'),
    path('experimentStart/',ExperimentStartView.as_view(),name='experiment_start'),
    path('experimentStatus/',ExperimentStatusView.as_view(),name='experiment_status'),
    path('experimentDetail/',ExperimentDetailView.as_view(),name='experiment_detail'),
    path('experimentStop/',ExperimentStopView.as_view(),name='experiment_stop'),
    path('experimentDelete/',ExperimentDeleteView.as_view(),name='experiment_delete'),
    path('experimentParentCheck/',ExperimentParentCheckView.as_view(),name='experiment_parent_check'),
    path('experimentTemplateCheck/',TemplateExperimentView.as_view(),name='experiment_template_check'),
    path('compressSimulation/',CompressSimulationView.as_view(),name='compress_simulation')
]

from .consumers import ExperimentConsumer
websocket_urlpatterns = [
    re_path(r'ws/experiment/(?P<sim_code>[^/]+)/$', ExperimentConsumer.as_asgi()),  # 使用正则表达式捕获 sim_code
]