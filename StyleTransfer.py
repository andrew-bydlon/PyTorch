from torchvision.models import vgg19
from collections import OrderedDict
import torch
import torch.nn as nn
import torch.optim as optim
import torchvision.transforms as transforms
from PIL import Image
from matplotlib.pyplot import gcf
import numpy as np
import matplotlib.pyplot as plt

imsize = 512
is_cuda = torch.cuda.is_available()

prep = transforms.Compose([transforms.Resize(imsize),
                           transforms.ToTensor(),
                           transforms.Lambda(lambda x: x[torch.LongTensor([2,1,0])]), #turn to BGR
                           transforms.Normalize(mean=[0.40760392, 0.45795686, 0.48501961], #subtract imagenet mean
                                                std=[1,1,1]),
                           transforms.Lambda(lambda x: x.mul_(255)),
                          ])
postpa = transforms.Compose([transforms.Lambda(lambda x: x.mul_(1./255)),
                           transforms.Normalize(mean=[-0.40760392, -0.45795686, -0.48501961], #add imagenet mean
                                                std=[1,1,1]),
                           transforms.Lambda(lambda x: x[torch.LongTensor([2,1,0])]), #turn to RGB
                           ])
postpb = transforms.Compose([transforms.ToPILImage()])


def imshow(inp, cmap=None):
    """Imshow for Tensor."""
    inp = np.asanyarray(inp)
    inp = inp.transpose((1, 2, 0))
    mean = np.array([0.485, 0.456, 0.406])
    std = np.array([0.229, 0.224, 0.225])
    inp = std * inp + mean
    inp = np.clip(inp, 0, 1)
    plt.imshow(inp,cmap)


def postp(tensor): # to clip results in the range [0,1]
    t = postpa(tensor)
    t[t>1] = 1
    t[t<0] = 0
    img = postpb(t)
    return img


def image_loader(image_name):
    image = Image.open(image_name)
    image = prep(image)
    # fake batch dimension required to fit network's input dimensions
    image = image.unsqueeze(0)
    return image


Image.open('Child.jpg').resize((600,600))

style_img = image_loader("starry_night.jpg")
content_img = image_loader("Child.jpg")
vgg = vgg19(pretrained=True).features
for param in vgg.parameters():
    param.requires_grad = False
if is_cuda:
    style_img = style_img.cuda()
    content_img = content_img.cuda()
    vgg = vgg.cuda()

opt_img = content_img.data.clone()
opt_img.requires_grad_()

style_layers = [1,6,11,20,25]
content_layers = [21]
loss_layers = style_layers + content_layers


class LayerActivations():
    features = []

    def __init__(self, model, layer_nums):

        self.hooks = []
        for layer_num in layer_nums:
            self.hooks.append(model[layer_num].register_forward_hook(self.hook_fn))

    def hook_fn(self, module, input, output):
        self.features.append(output)

    def remove(self):
        for hook in self.hooks:
            hook.remove()


class GramMatrix(nn.Module):

    def forward(self, input):
        b, c, h, w = input.size()
        features = input.view(b, c, h * w)
        gram_matrix = torch.bmm(features, features.transpose(1, 2))
        gram_matrix.div_(h * w)
        return gram_matrix


class StyleLoss(nn.Module):

    def forward(self, inputs, targets):
        out = nn.MSELoss()(GramMatrix()(inputs), targets)
        return (out)


def extract_layers(layers,img,model=None):
    la = LayerActivations(model,layers)
    #Clearing the cache
    la.features = []
    out = model(img)
    la.remove()
    return la.features


content_targets = extract_layers(content_layers,content_img,model=vgg)
content_targets = [t.detach() for t in content_targets]

style_targets = extract_layers(style_layers,style_img,model=vgg)
style_targets = [GramMatrix()(t).detach() for t in style_targets]

targets = style_targets + content_targets

loss_fns = [StyleLoss()] * len(style_layers) + [nn.MSELoss()] * len(content_layers)
if is_cuda:
    loss_fns = [fn.cuda() for fn in loss_fns]

style_weights = [1e3/n**2 for n in [64,128,256,512,512]]
content_weights = [1e0]
weights = style_weights + content_weights

max_iter = 500
show_iter = 50
optimizer = optim.LBFGS([opt_img]);
n_iter = [0]

while n_iter[0] <= max_iter:

    def closure():
        optimizer.zero_grad()

        out = extract_layers(loss_layers, opt_img, model=vgg)
        layer_losses = [weights[a] * loss_fns[a](A, targets[a]) for a, A in enumerate(out)]
        loss = sum(layer_losses)
        loss.backward()
        n_iter[0] += 1
        # print loss
        if n_iter[0] % show_iter == (show_iter - 1):
            print('Iteration: %d, loss: %f' % (n_iter[0] + 1, loss.data.item()))

        return loss


    optimizer.step(closure)

# save/display result
out_img_hr = postp(opt_img.data[0].cpu().squeeze())
out_img_hr.save('Manipulated_Child.jpg')
out_img_hr.show()
