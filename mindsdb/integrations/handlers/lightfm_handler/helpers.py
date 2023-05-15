import lightfm
import pandas as pd
import numpy as np
import scipy as sp
from pydantic import BaseModel
from collections import namedtuple
from enum import Enum
from typing import Optional, Dict, List, Union, Tuple

# possibly redundant
'''
def item_mapping(
		item_df: pd.DataFrame,
		item_id_column_name,
		item_description_column_name
) -> dict:
	"""

	takes in item metadata and creates a dict with key being mapped against the index and values being
	a namedtuple containing item id and product name. Creates an easy way to see what was predicted to a given user

	:param item_df:
	:param item_id_column_name:
	:param item_description_column_name:


	:return dict:
	"""
	item_map = {}
	item_data = namedtuple("ItemData", [item_id_column_name, item_description_column_name])

	for idx, item in enumerate(
			zip(
				item_df[item_id_column_name],
				item_df[item_description_column_name]
			)
	):
		item_map[idx] = item_data._make(item)

	return item_map
'''



def get_user_item_recommendations(n_users: int, n_items: int, args: dict, model: lightfm.LightFM):
	"""
	gets N user-item recommendations for a given model
	:param n_users:
	:param n_items:
	:param args:
	:param model:
	:return:
	"""
	# recommend items for each user

	user_ids = np.concatenate([np.full((n_items,), i) for i in range(0, n_users)])
	item_ids = np.concatenate([np.arange(n_items) for i in range(n_users)])

	scores = model.predict(user_ids, item_ids)

	# map scores to user-item pairs, sort by score and return top N recommendations per user
	user_item_recommendations_df = (
		pd.DataFrame({'user_id': user_ids, 'item_id': item_ids, 'score': scores})
		.groupby('user_id')
		.apply(lambda x: x.sort_values('score', ascending=False).head(args["n_recommendations"]))
	)

	return user_item_recommendations_df


def get_similar_items(item_idx: Union[int, str], model: lightfm.LightFM, item_features=None, N:int=10) -> pd.DataFrame:
	"""
	gets similar items to a given item index inside user-item interaction matrix
	NB by default it won't use item features,however if item features are provided
	it will use them to get similar items

	:param item_idx:
	:param model:
	:param item_features:
	:param N:

	:return:
	"""

	item_biases, item_representations = model.get_item_representations(features=item_features)

	# Cosine similarity
	# get scores for all items

	scores = item_representations.dot(item_representations[item_idx, :])

	# normalize

	item_norms = np.sqrt(( item_representations * item_representations).sum(axis=1))

	scores /= item_norms

	# get the top N items
	best = np.argpartition(scores, -N)
	# sort the scores

	rec = sorted(zip(best, scores[best] / item_norms[item_idx]), key=lambda x: -x[1])

	return (
		pd.DataFrame(rec, columns=['item_idx', 'score'])
		.tail(-1) # remove the item itself
		.head(N)
	)


class ModelParameters(BaseModel):
    learning_rate: float = 0.05
    loss: str = 'warp'
    epochs: int = 10


class RecommenderType(Enum):
	cf = 1
	hybrid = 2


# todo add support for hybrid recommender
class RecommenderPreprocessorOutput(BaseModel):
	interaction_df: pd.DataFrame
	interaction_matrix: sp.sparse.coo_matrix
	idx_item_map: dict
	idx_user_map: dict


	class Config:
		arbitrary_types_allowed = True


class RecommenderPreprocessor:

	def __init__(
			self,
			interaction_data: pd.DataFrame,
			user_id_column_name: str,
			item_id_column_name: str,
			threshold: int = 4,
			recommender_type=RecommenderType.cf
	):
		self.interaction_data = interaction_data
		self.user_id_column_name = user_id_column_name
		self.item_id_column_name = item_id_column_name
		self.threshold = threshold
		self.recommender_type = recommender_type

	@property
	def n_users_items(self):
		"""
		get tuple with number of users and items e.g. user-item matrix shape
		:return tuple:
		"""

		return (
			self.interaction_data[self.user_id_column_name].nunique(),
			self.interaction_data[self.item_id_column_name].nunique()
		)

	@property
	def _idx_item_map(
			self
	) -> dict:
		"""
		maps item idx in matrix to item id
		:return void:
		"""

		return (
			self.interaction_data[[self.item_id_column_name, 'item_idx']]
			.drop_duplicates()
			.set_index('item_idx')
			.to_dict()[self.item_id_column_name]
		)

	@property
	def _idx_user_map(
			self
	) -> dict:
		"""
		maps user idx in matrix to user id
		:return void:
		"""

		return (
			self.interaction_data[[self.user_id_column_name, 'user_idx']]
			.drop_duplicates()
			.set_index('user_idx')
			.to_dict()[self.user_id_column_name]
		)

	def map_id_to_idx(self):
		"""
		map user and item ids to a range of 0 to n_users and 0 to n_items respectively
		reduces density of user-item matrix
		:return void:
		"""

		unique_user_ids = {v: k for k, v in enumerate(self.interaction_data[self.user_id_column_name].unique(), 0)}
		unique_item_ids = {v: k for k, v in enumerate(self.interaction_data[self.item_id_column_name].unique(), 0)}

		self.interaction_data['user_idx'] = self.interaction_data[self.user_id_column_name].map(unique_user_ids)
		self.interaction_data['item_idx'] = self.interaction_data[self.item_id_column_name].map(unique_item_ids)

	def encode_interactions(self):
		"""
		set whether user interacted positively or negatively with item,
		negative may not be applicable depending on the use case
		:return void:
		"""
		# encode interactions as 1 or -1 for positive and negative respectively
		self.interaction_data['interaction'] = np.where(self.interaction_data.rating >= self.threshold, 1, -1).astype('int64')

	def construct_interaction_matrix(self) -> sp.sparse.coo_matrix:

		"""
		construct user x item interaction matrix
		:return sp.sparse.coo_matrix :
		"""

		lil_matrix = sp.sparse.lil_matrix(self.n_users_items)

		# populate the matrix
		for index, series in self.interaction_data[
			['user_idx', 'item_idx', 'interaction']].iterrows():
			lil_matrix[series['user_idx'], series['item_idx']] = series[
				'interaction']

		# convert from lil_matrix to coo_matrix

		return lil_matrix.tocoo()

	def preprocess(self) -> RecommenderPreprocessorOutput:
		"""
		runs a series of preprocessing tasks for recommender
		:return RecommenderPreprocessorOutput:
		"""
		# encode interactions
		self.encode_interactions()

		# get the idx of the user and item
		self.map_id_to_idx()

		# construct interaction matrix
		interaction_matrix = self.construct_interaction_matrix()

		return RecommenderPreprocessorOutput(
			interaction_df=self.interaction_data,
			interaction_matrix=interaction_matrix,
			idx_item_map=self._idx_item_map,
			idx_user_map=self._idx_user_map
		)

