import mlconfig
import torch
from torch import nn

class convolution(nn.Module):
    def __init__(self, in_channels, out_channels, kernel_size=3, stride=1):
        super(convolution, self).__init__()

        padding = (kernel_size - 1) // 2
        self.conv = nn.Conv2d(in_channels, out_channels, kernel_size, padding, stride)
        self.bn   = nn.BatchNorm2d(out_channels)
        self.relu = nn.ReLU(inplace=True)

    def forward(self, x):
        x = self.conv(x)
        x   = self.bn(x)
        x = self.relu(x)
        return x

class residual(nn.Module):
    
    def __init__(self, in_channels, out_channels, kernel_size=3, padding=1, stride=1):
        super(residual, self).__init__()

        self.conv1 = nn.Conv2d(in_channels, out_channels, kernel_size, padding, stride, bias=False)
        self.bn1   = nn.BatchNorm2d(out_channels)
        self.relu1 = nn.ReLU(inplace=True)

        self.conv2 = nn.Conv2d(out_channels, out_channels, kernel_size, padding, 1, bias=False)
        self.bn2   = nn.BatchNorm2d(out_channels)
        
        self.skip  = nn.Sequential(
            nn.Conv2d(in_channels, out_channels, 1, stride, padding, bias=False),
            nn.BatchNorm2d(out_channels)
        ) if stride != 1 or in_channels != out_channels else nn.Sequential()
        self.relu  = nn.ReLU(inplace=True)

    def forward(self, x):
        conv1 = self.conv1(x)
        bn1   = self.bn1(conv1)
        relu1 = self.relu1(bn1)

        conv2 = self.conv2(relu1)
        bn2   = self.bn2(conv2)

        skip  = self.skip(x)
        return self.relu(bn2 + skip)

def make_layer(in_channels, out_channels, kernel_size, modules, **kwargs):
    layers = [residual(in_channels, out_channels, kernel_size, **kwargs)]
    for _ in range(modules - 1):
        layers.append(residual(in_channels, out_channels, kernel_size, **kwargs))
    return nn.Sequential(*layers)

def make_hg_layer(in_channels, out_channels, kernel_size, modules, **kwargs):
    layers  = [residual(in_channels, out_channels, kernel_size, stride=2)]
    for _ in range(modules - 1):
        layers += [residual(in_channels, out_channels, kernel_size)]
    return nn.Sequential(*layers)

def make_layer_revr(in_channels, out_channels, kernel_size, modules, **kwargs):
    layers = []
    for _ in range(modules - 1):
        layers.append(residual(in_channels, out_channels, kernel_size, **kwargs))
    layers.append(residual(in_channels, out_channels, kernel_size, **kwargs))
    return nn.Sequential(*layers)


class kp_module(nn.Module):
    def __init__(self, n, channels, modules, **kwargs):
        super(kp_module, self).__init__()
        self.n   = n

        curr_mod = modules[0]
        next_mod = modules[1]

        curr_channels = channels[0]
        next_channels = channels[1]

        # 将输入进来的特征层进行两次残差卷积，便于和后面的层进行融合
        self.up1  = make_layer(
            3, curr_channels, curr_channels, curr_mod, **kwargs
        )  
        # 进行下采样
        self.low1 = make_hg_layer(
            3, curr_channels, next_channels, curr_mod, **kwargs
        )

        # 构建U形结构的下一层
        if self.n > 1 :
            self.low2 = kp_module(
                n - 1, channels[1:], modules[1:], **kwargs
            ) 
        else:
            self.low2 = make_layer(
                3, next_channels, next_channels, next_mod, **kwargs
            )

        # 将U形结构下一层反馈上来的层进行残差卷积
        self.low3 = make_layer_revr(
            3, next_channels, curr_channels, curr_mod, **kwargs
        )
        # 将U形结构下一层反馈上来的层进行上采样
        self.up2  = nn.Upsample(scale_factor=2)

    def forward(self, x):
        up1  = self.up1(x)
        low1 = self.low1(x)
        low2 = self.low2(low1)
        low3 = self.low3(low2)
        up2  = self.up2(low3)
        outputs = up1 + up2
        return outputs