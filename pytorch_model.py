# -*- coding: utf-8 -*-
"""Pytorch_model.ipynb

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/1OkHgIfVdY709P9FCRBg7VKoLjdCV-A-I
"""

!pip install albumentations==0.4.6
!pip install timm

import sys
import os
import random
import json
import gc
import cv2
import pandas as pd
import numpy as np
import tensorflow as tf

from tqdm import tqdm
from PIL import Image
from sklearn.metrics import accuracy_score
from functools import partial
from albumentations import (Compose, OneOf, Normalize, Resize, RandomResizedCrop, RandomCrop, CenterCrop,
                            HorizontalFlip, VerticalFlip, Rotate, ShiftScaleRotate, Transpose)
from albumentations.pytorch import ToTensorV2
from albumentations import ImageOnlyTransform

from tensorflow import keras

# sys.path.append('../input/timm-pytorch-image-models/pytorch-image-models-master')
# sys.path.append('../input/pytorch-image-models/pytorch-image-models-master')

import timm
import torch
import torch.nn as nn
import torch.nn.functional as F
import torchvision.models as models
from torch.utils.data import DataLoader, Dataset

gcs_path = 'gs://kds-b13be1d28e388a5c393bd7de0f606ef8ee7a3455ef489dc10f3528c4'

cd drive/MyDrive/kaggle/

ls

os.getcwd()

os.environ['KAGGLE_CONFIG_DIR'] = '..'

! chmod 600 ./kaggle.json # to set file permissions

# !kaggle datasets download -d 'jannish/cassava-leaf-disease-1st-place-models'
# !kaggle datasets download -d kozodoi/timm-pytorch-image-models
!kaggle datasets download -d yasufuminakama/pytorch-image-models

os.getcwd()

cd '/drive/MyDrive/kaggle'

mkdir 'cassava-leaf-disease-data'

cd cassava-leaf-disease-data/

!kaggle competitions download -c cassava-leaf-disease-classification

os.getcwd()

ls

cd /content/

# Complete path to storage location of the unzipped file(FOLDER) of data
unzipped_path = '/content/drive/MyDrive/kaggle/cassava-leaf-disease-1st-place-models'
# Check current directory (be sure you're in the directory where Colab operates: '/content')
os.getcwd()
# Copy the .zip file into the present directory
!cp -r '{unzipped_path}' . # -r flag is necessary for recursive copying 📌⚠️
# Unzip quietly
# !unzip -q 'cassava-leaf-disease-1st-place-models'
# View the unzipped contents in the virtual machine
os.listdir()

# Complete path to storage location of the unzipped file(FOLDER) of data
unzipped_path = '/content/drive/MyDrive/kaggle/cassava-leaf-disease-data'
# Check current directory (be sure you're in the directory where Colab operates: '/content')
os.getcwd()
# Copy the .zip file into the present directory
!cp -r '{unzipped_path}' . # -r flag is necessary for recursive copying 📌⚠️
# Unzip quietly
# !unzip -q 'cassava-leaf-disease-1st-place-models'
# View the unzipped contents in the virtual machine
os.listdir()

GCS_PATH = 'gs://kds-1bacd121294cd480b590984af7396af1200003223b41e3c3b19222c2'

os.getcwd()

cd '/content'

path = "/content/cassava-leaf-disease-data/"
# path = "/content/drive/MyDrive/kaggle/cassava-leaf-disease-data"
image_path = path# + "test_images/"

IMAGE_SIZE = (512,512)
submission_df = pd.DataFrame(columns={"image_id","label"})
submission_df["image_id"] = os.listdir(image_path)
submission_df["label"] = 0

# We used this flag to test combinations using only TF.Keras models
onlykeras = False

used_models_pytorch = {"vit2020": [f'/content/cassava-leaf-disease-1st-place-models/vit/vit_base_patch16_384_fold_{fold}.h5' for fold in [0,1,2,3,4]],
                       "resnext": [f'/content/cassava-leaf-disease-1st-place-models/resnext50_32x4d/resnext50_32x4d_fold{fold}_best.pth' for fold in [0,1,2,3,4]]}

used_models_keras = {"mobilenet": "/content/cassava-leaf-disease-1st-place-models/cropnet_mobilenetv3/cropnet",
                     "efficientnetb4": "/content/cassava-leaf-disease-1st-place-models/efficientnetb4/efficientnetb4_all_e14.h5"}

# We used this flag for testing different ensembling approaches
stacked_mean = True

"""# RESNEXT"""

class CustomResNext(nn.Module):
        def __init__(self, model_name='resnext50_32x4d', pretrained=False):
            super().__init__()
            self.model = timm.create_model(model_name, pretrained=pretrained)
            n_features = self.model.fc.in_features
            self.model.fc = nn.Linear(n_features, 5)

        def forward(self, x):
            x = self.model(x)
            return x

class TestDataset(Dataset):
    def __init__(self, df, transform=None):
        self.df = df
        self.file_names = df['image_path_id'].values
        self.transform = transform

    def __len__(self):
        return len(self.df)

    def __getitem__(self, idx):
        file_name = self.file_names[idx]
        image = cv2.imread(file_name)
        image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        if self.transform:
            augmented = self.transform(image=image)
            image = augmented['image']
        return image

if "resnext" in used_models_pytorch:
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

    def get_transforms():
        return Compose([Resize(512, 512),
                        Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
                        ToTensorV2()])

    def inference(model, states, test_loader, device):
        model.to(device)

        probabilities = []
        for i, (images) in enumerate(test_loader):
            images = images.to(device)
            avg_preds = []
            for state in states:
                model.load_state_dict(state['model'])
                model.eval()
                with torch.no_grad():
                    y_preds = model(images)
                avg_preds.append(y_preds.softmax(1).to('cpu').numpy())
            avg_preds = np.mean(avg_preds, axis=0)
            probabilities.append(avg_preds)
        return np.concatenate(probabilities)


    predictions_resnext = pd.DataFrame(columns={"image_id"})
    predictions_resnext["image_id"] = submission_df["image_id"].values
    predictions_resnext['image_path_id'] = image_path + predictions_resnext['image_id'].astype(str)

    model = CustomResNext('resnext50_32x4d', pretrained=False)
    states = [torch.load(f) for f in used_models_pytorch["resnext"]]

    test_dataset = TestDataset(predictions_resnext, transform=get_transforms())
    test_loader = DataLoader(test_dataset, batch_size=16, shuffle=False, num_workers=4, pin_memory=True)
    predictions = inference(model, states, test_loader, device)

    predictions_resnext['resnext'] = [np.squeeze(p) for p in predictions]
    predictions_resnext = predictions_resnext.drop(["image_path_id"], axis=1)


    torch.cuda.empty_cache()
    try:
        del(model)
        del(states)
    except:
        pass
    gc.collect()

if "vit2020" in used_models_pytorch:

    vit_image_size = 384

    class CustomViT(nn.Module):
        def __init__(self, model_arch, n_class, pretrained=False):
            super().__init__()
            self.model = timm.create_model(model_arch, pretrained=pretrained)
            n_features = self.model.head.in_features
            self.model.head = nn.Linear(n_features, n_class)

        def forward(self, x):
            x = self.model(x)
            return x

    class TestDataset(Dataset):
        def __init__(self, df, transform=None):
            self.df = df
            self.file_names = df['image_path_id'].values
            self.transform = transform

        def __len__(self):
            return len(self.df)

        def __getitem__(self, idx):
            file_name = self.file_names[idx]
            im_bgr = cv2.imread(file_name)
            image = im_bgr[:, :, ::-1]
            if self.transform:
                augmented = self.transform(image=image)
                image = augmented['image']
            return image

    def get_tta_transforms():
        return Compose([CenterCrop(vit_image_size, vit_image_size, p=1.),
                Resize(vit_image_size, vit_image_size),
                Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225], max_pixel_value=255.0, p=1.0),
                ToTensorV2(p=1.0)], p=1.)

    def inference(models, test_loader, device):
        tk0 = tqdm(enumerate(test_loader), total=len(test_loader))
        probs = []
        for i, (images) in tk0:
            avg_preds = []
            for model in models:
                images = images.to(device)
                model.to(device)
                model.eval()
                with torch.no_grad():
                    y_preds = model(images)
                avg_preds.append(y_preds.softmax(1).to('cpu').numpy())
            avg_preds = np.mean(avg_preds, axis=0)
            probs.append(avg_preds)
        probs = np.concatenate(probs)
        return probs

    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

    predictions_vit = pd.DataFrame(columns={"image_id"})
    predictions_vit["image_id"] = submission_df["image_id"].values
    predictions_vit['image_path_id'] = image_path + predictions_vit['image_id'].astype(str)

    def load_cassava_vit(modelpath):
        _model = CustomViT('vit_base_patch16_384', 5, pretrained=False)
        _model.load_state_dict(torch.load(modelpath))
        _model.eval()
        return _model

    models = [load_cassava_vit(f) for f in used_models_pytorch["vit2020"]]

    test_dataset = TestDataset(predictions_vit, transform=get_tta_transforms())
    test_loader = DataLoader(test_dataset, batch_size=32, shuffle=False, num_workers=4, pin_memory=True)

    predictions_raw_vit = inference(models, test_loader, device)

    predictions_vit['vit2020'] = [np.squeeze(p) for p in predictions_raw_vit]
    predictions_vit = predictions_vit.drop(["image_path_id"], axis=1)

    torch.cuda.empty_cache()
    try:
        for model in models:
            del(model)
    except:
        pass
    models = []
    gc.collect()

import tensorflow_hub as hub

def build_mobilenet3(img_size=(224,224), weights="../input/cassava-leaf-disease-1st-place-models/cropnet_mobilenetv3/cropnet"):
    classifier = hub.KerasLayer(weights)
    model = tf.keras.Sequential([
    tf.keras.layers.InputLayer(input_shape=img_size + (3,)),
    hub.KerasLayer(classifier, trainable=False)])
    return model

def image_augmentations(image):
    p_spatial = tf.random.uniform([], 0, 1.0, dtype = tf.float32)
    p_rotate = tf.random.uniform([], 0, 1.0, dtype = tf.float32)

    image = tf.image.random_flip_left_right(image)
    image = tf.image.random_flip_up_down(image)

    if p_spatial > 0.75:
        image = tf.image.transpose(image)

    if p_rotate > 0.75:
        image = tf.image.rot90(image, k = 3)
    elif p_rotate > 0.5:
        image = tf.image.rot90(image, k = 2)
    elif p_rotate > 0.25:
        image = tf.image.rot90(image, k = 1)

    image = tf.image.resize(image, size = IMAGE_SIZE)
    image = tf.reshape(image, [*IMAGE_SIZE, 3])

    return image

def read_preprocess_file(img_path, normalize=False):
    image = Image.open(img_path)
    if normalize:
        img_scaled = np.array(image)/ 255.0
    else:
        img_scaled = np.array(image)
    img_scaled = img_scaled.astype(np.float32)
    return (image.size[0], image.size[1]), img_scaled

def create_image_tiles(origin_dim, processed_img):
    crop_size = 512
    img_list = []
    # Cut image into 4 overlapping patches
    for x in [0, origin_dim[1] - crop_size]:
        for y in [0, origin_dim[0] - crop_size]:
            img_list.append(processed_img[x:x+crop_size , y:y+crop_size,:])
    # Keep one additional center cropped image
    img_list.append(cv2.resize(processed_img[:, 100:700 ,:], dsize=(crop_size, crop_size)))
    return np.array(img_list)

def augment_tiles_light(tiles, ttas=2):
  # Copy central croped image to have same ratio to augmented images
  holdout = np.broadcast_to(tiles[-1,:,:,:],(ttas,) + tiles.shape[1:])
  augmented_batch = tf.map_fn(lambda x: image_augmentations(x), tf.concat(
      [tiles[:-1,:,:,:] for _ in range(ttas)], axis=0))
  return tf.concat([augmented_batch, holdout], axis=0)

def cut_crop_image(processed_img):
    image = tf.image.central_crop(processed_img, 0.8)
    image = tf.image.resize(image, (224, 224))
    return np.expand_dims(image, 0)

# CropNet class 6 (unknown) is distributed evenly over all 5 classes to match problem setting
def distribute_unknown(propabilities):
    return propabilities[:,:-1] + np.expand_dims(propabilities[:,-1]/5, 1)

def multi_predict_tfhublayer(img_path, modelinstance):
    img = cut_crop_image(read_preprocess_file(img_path, True)[1])
    yhat = modelinstance.predict(img)
    return np.mean(distribute_unknown(yhat), axis=0)

def multi_predict_keras(img_path, modelinstance, *args):
    augmented_batch = augment_tiles_light(create_image_tiles(
        *read_preprocess_file(img_path)))
    Yhat = modelinstance.predict(augmented_batch)
    return np.mean(Yhat, axis=0)

def predict_and_vote(image_list, modelinstances, onlykeras):
    predictions = []
    with tqdm(total=len(image_list)) as process_bar:
      for img_path in image_list:
        process_bar.update(1)
        Yhats = np.vstack([func(img_path, modelinstance) for func, modelinstance in modelinstances])
        if onlykeras:
            predictions.append(np.argmax(np.sum(Yhats, axis=0)))
        else:
            predictions.append(Yhats)
    return predictions


inference_models = []

if "mobilenet" in used_models_keras:
    model_mobilenet = build_mobilenet3(weights=used_models_keras["mobilenet"])
    inference_models.append((multi_predict_tfhublayer, model_mobilenet))

if "efficientnetb4" in used_models_keras:
    model_efficientnetb4 =  keras.models.load_model(used_models_keras["efficientnetb4"], compile=False)
    inference_models.append((multi_predict_keras, model_efficientnetb4))

if "efficientnetb5" in used_models_keras:
    model_efficientnetb5 =  keras.models.load_model(used_models_keras["efficientnetb5"])
    inference_models.append((multi_predict_keras, model_efficientnetb5))

submission_df["label"] = predict_and_vote([image_path+id for id in submission_df["image_id"].values], inference_models, onlykeras)

tf.keras.backend.clear_session()

try:
    del inference_models[:]
except:
    pass

gc.collect()

if len(list(used_models_keras.keys())) <= 1:
    submission_df.loc[:,list(used_models_keras)[0]] = submission_df["label"].explode()
else:
    tmp = (submission_df['label'].transform([lambda x:x[0], lambda x:x[1]]).set_axis(list(used_models_keras.keys()), axis=1, inplace=False))
    submission_df = submission_df.merge(tmp, right_index=True, left_index=True)

submission_df["label"] = 0

if "resnext" in used_models_pytorch:
    submission_df = submission_df.merge(predictions_resnext, on="image_id")

if "efficientnetb3" in used_models_pytorch:
    submission_df = submission_df.merge(predictions_cutmix, on="image_id")

if "vit2020" in used_models_pytorch:
    submission_df = submission_df.merge(predictions_vit, on="image_id")

if "vit2019" in used_models_pytorch:
    submission_df = submission_df.merge(predictions_vit2019, on="image_id")

if stacked_mean:
    submission_df["stage_1"] = submission_df.apply(lambda row: [np.mean(e) for e in zip(row["vit2020"], row["resnext"])], axis=1)
    submission_df["label"] = submission_df.apply(lambda row: np.argmax(
        [np.sum(e) for e in zip(row["mobilenet"],row["stage_1"], row["efficientnetb4"])]), axis=1)
else:
    submission_df["label"] = submission_df.apply(lambda row: np.argmax(
        [np.sum(e) for e in zip(*[row[m] for m in list(used_models_pytorch.keys())+list(used_models_keras.keys())])]), axis=1)

submission_df.head(1)

submission_df[["image_id","label"]].to_csv("submission.csv", index=False)
!head submission.csv